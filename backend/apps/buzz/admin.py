from django.contrib import admin
from django.utils.html import format_html

from . import partner as pb
from .models import BuzzMedia, BuzzPost, BuzzReport


class MediaInline(admin.TabularInline):
    model = BuzzMedia
    extra = 0
    fields = ["preview", "kind", "width", "height", "bytes", "position"]
    readonly_fields = fields
    can_delete = False

    @admin.display(description="Media")
    def preview(self, m):
        url = pb.media_url(m, pb.IMAGE_WIDTHS[0])
        if not url:
            return "—"
        if m.kind == BuzzMedia.Kind.VIDEO:
            return format_html('<video src="{}" width="200" controls preload="none"></video>', url)
        return format_html('<img src="{}" width="160" alt="">', url)


@admin.register(BuzzPost)
class BuzzPostAdmin(admin.ModelAdmin):
    """Click moderation of partner Buzz posts: customers see a post only after approval."""

    list_display = ["headline", "partner", "kind", "status", "audience", "publish_at", "expires_at", "views", "cta_clicks", "likes", "open_reports"]
    list_filter = ["status", "kind", "audience"]
    search_fields = ["headline", "caption", "partner__business_name", "partner__partner_code"]
    readonly_fields = ["partner", "views", "cta_clicks", "likes", "saves", "submitted_at", "reviewed_at", "reviewed_by"]
    inlines = [MediaInline]
    actions = ["approve", "reject", "take_down"]

    @admin.display(description="Open reports")
    def open_reports(self, post):
        return post.reports.filter(status=BuzzReport.Status.OPEN).count()

    @admin.action(description="Approve (goes live on Buzz at its start time)")
    def approve(self, request, queryset):
        n = sum(1 for p in queryset.select_related("partner") if pb.review(p, True, request.user).status == BuzzPost.Status.APPROVED)
        self.message_user(request, f"{n} post(s) approved.")

    @admin.action(description="Reject (partner can edit and resubmit)")
    def reject(self, request, queryset):
        for p in queryset.select_related("partner"):
            pb.review(p, False, request.user, "This post doesn’t meet the Buzz guidelines. Check the claims, media and offer, then resubmit.")
        self.message_user(request, "Rejected posts sent back to the partner.")

    @admin.action(description="Take down (remove a live post)")
    def take_down(self, request, queryset):
        for p in queryset.select_related("partner"):
            pb.remove(p, "Click removed this post after review. Contact Partner support if you think this is a mistake.")
        self.message_user(request, "Posts removed.")


@admin.register(BuzzReport)
class BuzzReportAdmin(admin.ModelAdmin):
    list_display = ["post", "reason", "status", "reporter", "created_at"]
    list_filter = ["status", "reason"]
    actions = ["uphold", "dismiss"]

    @admin.action(description="Uphold: remove the post")
    def uphold(self, request, queryset):
        for r in queryset.select_related("post__partner"):
            if r.post.status != BuzzPost.Status.REMOVED:
                pb.remove(r.post, f"Removed after a report: {r.get_reason_display().lower()}.")
            r.post.reports.filter(status=BuzzReport.Status.OPEN).update(status=BuzzReport.Status.UPHELD)
        self.message_user(request, "Reports upheld.")

    @admin.action(description="Dismiss")
    def dismiss(self, request, queryset):
        queryset.update(status=BuzzReport.Status.DISMISSED)
