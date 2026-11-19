"""os/documents — upload, list, download, new version, verify, archive. Content is checked, not trusted."""

import hashlib
import mimetypes
from datetime import date

from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.access.api import OSView
from apps.audit.services import record
from apps.core.api.exceptions import DomainError

from . import access
from .models import Document, DocumentVersion

MAX_BYTES = 10 * 1024 * 1024
SIGNATURES = {  # magic bytes → content type; the browser's claim is ignored
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"RIFF": "image/webp",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def sniff(upload) -> str:
    head = upload.read(16)
    upload.seek(0)
    for sig, ctype in SIGNATURES.items():
        if head.startswith(sig):
            if ctype == "image/webp" and head[8:12] != b"WEBP":
                continue
            if ctype.endswith("document") and not upload.name.lower().endswith(".docx"):
                continue
            return ctype
    raise DomainError("Upload a PDF, JPG, PNG, WebP or Word (.docx) file.", code="file_type")


def _digest(upload) -> str:
    h = hashlib.sha256()
    for chunk in upload.chunks():
        h.update(chunk)
    upload.seek(0)
    return h.hexdigest()


def payload(d: Document, ctx=None) -> dict:
    v = d.versions.first()
    today = date.today()
    return {"id": str(d.pk), "title": d.title, "category": d.category, "module": d.module, "resource_type": d.resource_type,
            "resource_id": d.resource_id, "sensitivity": d.sensitivity, "expires_on": d.expires_on,
            "expiring": bool(d.expires_on and 0 <= (d.expires_on - today).days <= 30), "expired": bool(d.expires_on and d.expires_on < today),
            "verification": d.verification, "verified_at": d.verified_at, "status": d.status, "version": d.current_version,
            "file_name": v.file_name if v else None, "size": v.size if v else None, "content_type": v.content_type if v else None,
            "uploaded_by": d.uploaded_by.full_name if d.uploaded_by_id else None, "created_at": d.created_at, "updated_at": d.updated_at,
            "can_verify": bool(ctx and access.allowed(ctx, d.resource_type, d.resource_id, "verify", d))}


def _visible(ctx, d: Document) -> bool:
    return access.allowed(ctx, d.resource_type, d.resource_id, "view", d)


class DocumentsView(OSView):
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        ctx = self.authz
        rt, rid = request.query_params.get("resource_type", ""), request.query_params.get("resource_id", "")
        if not rt or not rid:
            raise DomainError("Choose the record whose documents to list.", code="validation_error")
        if not access.allowed(ctx, rt, rid, "view"):
            raise DomainError("Not found.", code="not_found", status_code=404)
        qs = Document.objects.filter(organization=ctx.organization, resource_type=rt, resource_id=rid).select_related("uploaded_by").prefetch_related("versions")
        if request.query_params.get("archived") != "true":
            qs = qs.filter(status=Document.Status.ACTIVE)
        docs = [d for d in qs if _visible(ctx, d)]  # per-document check: restricted files need more than the record
        return Response({"results": [payload(d, ctx) for d in docs],
                         "can_upload": access.allowed(ctx, rt, rid, "upload")})

    def post(self, request):
        ctx = self.authz
        d = request.data
        rt, rid = str(d.get("resource_type", "")), str(d.get("resource_id", ""))
        upload = request.FILES.get("file")
        if not access.allowed(ctx, rt, rid, "upload"):
            raise DomainError("You can’t add documents here.", code="permission_denied", status_code=403)
        if upload is None:
            raise DomainError("Choose a file.", code="validation_error", details={"file": ["Choose a file."]})
        if upload.size > MAX_BYTES:
            raise DomainError("Files must be 10 MB or smaller.", code="file_too_large")
        ctype = sniff(upload)
        sensitivity = d.get("sensitivity") if d.get("sensitivity") in Document.Sensitivity.values else Document.Sensitivity.CONFIDENTIAL
        probe = Document(resource_type=rt, resource_id=rid, sensitivity=sensitivity)
        if sensitivity == Document.Sensitivity.RESTRICTED and not access.allowed(ctx, rt, rid, "upload_restricted", probe):
            raise DomainError("You can’t add restricted documents here.", code="permission_denied", status_code=403)
        title = str(d.get("title") or upload.name).strip()[:160]
        with transaction.atomic():
            doc = Document.objects.create(organization=ctx.organization, module=rt.split(".")[0], resource_type=rt, resource_id=rid,
                                          category=str(d.get("category") or "other")[:40], title=title, sensitivity=sensitivity,
                                          expires_on=parse_date(str(d.get("expires_on") or "")) or None, uploaded_by=request.user)
            DocumentVersion.objects.create(document=doc, version=1, file=upload, file_name=upload.name[:200], content_type=ctype,
                                           size=upload.size, sha256=_digest(upload), uploaded_by=request.user)
        record(request, "documents.upload", category="data", module=doc.module, resource=doc,
               new={"title": doc.title, "category": doc.category, "resource": f"{rt}:{rid}"}, sensitive=sensitivity != "normal")
        return Response(payload(doc, ctx), status=status.HTTP_201_CREATED)


def _doc_for(ctx, pk, action="view") -> Document:
    doc = Document.objects.filter(pk=pk, organization=ctx.organization).select_related("uploaded_by").first()
    if doc is None or not _visible(ctx, doc):
        raise DomainError("Not found.", code="not_found", status_code=404)
    if action != "view" and not access.allowed(ctx, doc.resource_type, doc.resource_id, action, doc):
        raise DomainError("You can’t do this with this document.", code="permission_denied", status_code=403)
    return doc


class DocumentDetailView(OSView):
    def get(self, request, pk):
        doc = _doc_for(self.authz, pk)
        data = payload(doc, self.authz)
        data["versions"] = [{"version": v.version, "file_name": v.file_name, "size": v.size, "uploaded_by": v.uploaded_by.full_name if v.uploaded_by_id else None,
                             "created_at": v.created_at, "note": v.note} for v in doc.versions.select_related("uploaded_by")]
        return Response(data)


class DocumentDownloadView(OSView):
    def get(self, request, pk):
        doc = _doc_for(self.authz, pk)
        n = request.query_params.get("version")
        v = doc.versions.filter(version=int(n)).first() if n and n.isdigit() else doc.versions.first()
        if v is None:
            raise DomainError("Not found.", code="not_found", status_code=404)
        if doc.sensitivity != Document.Sensitivity.NORMAL:  # viewing confidential files is audited
            record(request, "documents.download", category="data", module=doc.module, resource=doc, sensitive=True,
                   metadata={"version": v.version})
        resp = FileResponse(v.file.open("rb"), content_type=v.content_type or mimetypes.guess_type(v.file_name)[0] or "application/octet-stream")
        resp["Content-Disposition"] = f'inline; filename="{v.file_name}"'
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-store"
        return resp


class DocumentVersionView(OSView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        doc = _doc_for(self.authz, pk, "upload")
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Choose a file.", code="validation_error")
        if upload.size > MAX_BYTES:
            raise DomainError("Files must be 10 MB or smaller.", code="file_too_large")
        ctype = sniff(upload)
        with transaction.atomic():
            doc = Document.objects.select_for_update().get(pk=doc.pk)
            doc.current_version += 1
            doc.verification, doc.verified_by, doc.verified_at = Document.Verification.UNVERIFIED, None, None
            if request.data.get("expires_on"):
                doc.expires_on = parse_date(str(request.data["expires_on"]))
            doc.save()
            DocumentVersion.objects.create(document=doc, version=doc.current_version, file=upload, file_name=upload.name[:200], content_type=ctype,
                                           size=upload.size, sha256=_digest(upload), uploaded_by=request.user, note=str(request.data.get("note", ""))[:200])
        record(request, "documents.version", category="data", module=doc.module, resource=doc, metadata={"version": doc.current_version},
               sensitive=doc.sensitivity != "normal")
        return Response(payload(doc, self.authz), status=status.HTTP_201_CREATED)


class DocumentActionView(OSView):
    def post(self, request, pk, action):
        if action not in ("verify", "reject", "archive", "restore"):
            raise DomainError("Not found.", code="not_found", status_code=404)
        doc = _doc_for(self.authz, pk, "verify" if action in ("verify", "reject") else "archive")
        before = {"verification": doc.verification, "status": doc.status}
        if action in ("verify", "reject"):
            doc.verification = Document.Verification.VERIFIED if action == "verify" else Document.Verification.REJECTED
            doc.verified_by, doc.verified_at = request.user, timezone.now()
        elif action == "archive":
            if doc.retain_until and doc.retain_until > date.today():
                pass  # archiving hides it; it is still retained
            doc.status = Document.Status.ARCHIVED
        else:
            doc.status = Document.Status.ACTIVE
        doc.save()
        record(request, f"documents.{action}", category="data", module=doc.module, resource=doc, old=before,
               new={"verification": doc.verification, "status": doc.status})
        return Response(payload(doc, self.authz))
