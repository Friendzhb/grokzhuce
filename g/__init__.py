"""
注册机配件
"""
from .email_service import EmailService
from .turnstile_service import TurnstileService
from .user_agreement_service import UserAgreementService
from .nsfw_service import NsfwSettingsService
from .flaresolverr_service import FlareSolverrService
from .browser_register import register_one as browser_register_one

__all__ = [
    'EmailService',
    'TurnstileService',
    'UserAgreementService',
    'NsfwSettingsService',
    'FlareSolverrService',
    'browser_register_one',
]
