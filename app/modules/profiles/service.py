"""Private profiles, owner-only avatar metadata and exam eligibility."""
from app.models import User,Event
from sqlalchemy import select
from app.errors import Problem

def complete(user):
    return bool(user and user.full_name and user.cccd and (user.email or user.pending_email))

def avatar_url(user):
    return '/me/avatar?v='+user.avatar_key.rsplit('/',1)[-1] if user.avatar_key else None

def output(user):
    return {k:getattr(user,k) for k in ('full_name','cccd','phone')} | {'email':user.pending_email or user.email,'pending_email':user.pending_email,'email_verified':bool(user.email_verified_at) and not user.pending_email,'profile_complete':complete(user),'avatar_url':avatar_url(user)}

def require_for_exam(db,user_id,lab):
    from app.modules.accounts.service import eligible
    eligible(db,user_id,lab)


def cleanup_avatar_after_commit(db,adapter,key):
    # References are removed in the caller transaction. The common collector
    # quarantines orphaned objects before deletion, including replaced avatars.
    return
