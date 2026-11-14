"""DRF error messages that DRF's own Polish catalogue does not translate.

This module is never imported. It only lists the msgids so that
``makemessages`` keeps them in ``locale/*/LC_MESSAGES/django.po``; the project
catalogue (LOCALE_PATHS) takes precedence over DRF's, so the translations here
are used at runtime. Each string must match DRF's msgid exactly.
"""

from django.utils.translation import gettext_noop

DRF_MESSAGES = [
    gettext_noop("A valid biginteger is required."),
    gettext_noop("Datetime value out of range."),
    gettext_noop("Ensure this field has at least {min_length} elements."),
    gettext_noop("Ensure this field has no more than {max_length} elements."),
    gettext_noop(
        'Enter a valid "slug" consisting of Unicode letters, numbers, underscores, or hyphens.'
    ),
    gettext_noop("Integer value too large to convert to float"),
    gettext_noop('Invalid datetime for the timezone "{timezone}".'),
    gettext_noop("Must be a valid UUID."),
    gettext_noop("Must be a valid boolean."),
    gettext_noop("Not a valid string."),
    gettext_noop("Surrogate characters are not allowed: U+{code_point:X}."),
    gettext_noop("The number of days must be between {min_days} and {max_days}."),
    gettext_noop("This dictionary may not be empty."),
]
