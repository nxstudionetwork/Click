import logging

from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.activity.services import record
from apps.core.api.exceptions import ConflictError, DomainError
from apps.customers.models import MAX_ADDRESSES, CustomerProfile
from apps.customers.serializers import AddressSerializer
from apps.notifications.models import NotificationCategory
from apps.notifications.services import notify
from apps.users.models import User

from .models import ExternalIdentity
from .providers import VerifiedIdentity

audit = logging.getLogger("click.audit")
SIGNUP_SALT = "click.identity.signup"
SIGNUP_MAX_AGE = 20 * 60  # seconds the customer has to finish their profile after OTP


def resolve_user(identity: VerifiedIdentity) -> User | None:
    """Same provider subject -> same Click user, always. A verified phone already on an account links back to it."""
    link = ExternalIdentity.objects.select_related("user").filter(provider=identity.provider, subject=identity.subject).first()
    if link:
        ExternalIdentity.objects.filter(pk=link.pk).update(last_verified_at=timezone.now(), phone_number=identity.phone_number)
        return link.user if link.user.is_active else None
    user = User.objects.filter(phone=identity.phone_number, phone_verified=True, is_active=True).first()
    if user:
        with transaction.atomic():
            ExternalIdentity.objects.create(user=user, provider=identity.provider, subject=identity.subject,
                                            phone_number=identity.phone_number, last_verified_at=timezone.now())
        audit.info("identity.linked_by_verified_phone", extra={"user_id": str(user.id), "provider": identity.provider})
        return user
    return None


def issue_signup_token(identity: VerifiedIdentity) -> str:
    return signing.dumps({"p": identity.provider, "s": identity.subject, "ph": identity.phone_number}, salt=SIGNUP_SALT)


def read_signup_token(token: str) -> VerifiedIdentity:
    try:
        data = signing.loads(token, salt=SIGNUP_SALT, max_age=SIGNUP_MAX_AGE)
    except signing.SignatureExpired:
        raise DomainError("Your verification expired. Please verify your phone again.", code="signup_expired", status_code=401)
    except signing.BadSignature:
        raise DomainError("Invalid signup session. Please verify your phone again.", code="signup_invalid", status_code=401)
    return VerifiedIdentity(provider=data["p"], subject=data["s"], phone_number=data["ph"])


@transaction.atomic
def complete_signup(identity: VerifiedIdentity, *, full_name: str, email: str, addresses: list[dict]) -> tuple[User, bool]:
    """Creates User + CustomerProfile (Click ID) + identity link + addresses. Idempotent per identity."""
    existing = resolve_user(identity)
    if existing:
        return existing, False
    if not 1 <= len(addresses) <= MAX_ADDRESSES:
        raise DomainError(f"Add between 1 and {MAX_ADDRESSES} addresses.", code="invalid_address_count")
    if User.objects.filter(email__iexact=email).exists():
        raise ConflictError("This email is already used by another Click account.", code="email_taken", details={"email": ["Already in use."]})
    try:
        user = User.objects.create_user(email, None, full_name=full_name, phone=identity.phone_number, phone_verified=True)
        profile = CustomerProfile.objects.create(user=user)
        ExternalIdentity.objects.create(user=user, provider=identity.provider, subject=identity.subject,
                                        phone_number=identity.phone_number, last_verified_at=timezone.now())
    except IntegrityError:
        raise ConflictError("This phone or email is already linked to a Click account.", code="identity_conflict")
    for i, data in enumerate(addresses):
        s = AddressSerializer(data={**data, "is_default": i == 0})
        s.is_valid(raise_exception=True)
        s.save(customer=profile)
    notify(profile, NotificationCategory.SYSTEM, "Welcome to Click!", f"Your Click ID is {profile.customer_code}.", "/account")
    record(profile, "account.signup", {"provider": identity.provider})
    audit.info("identity.signup", extra={"user_id": str(user.id), "provider": identity.provider})
    return user, True
