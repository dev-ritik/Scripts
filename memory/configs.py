from provider.diary_provider import DiaryProvider
from provider.google_photos_provider import GooglePhotosProvider
from provider.immich_provider import ImmichProvider
from provider.instagram_provider import InstagramProvider
from provider.whatsapp_provider import WhatsAppProvider

# This file has all the customizations for setups

USER = "Ritik"

AVAILABLE_PROVIDERS = [
    WhatsAppProvider,
    InstagramProvider,
    DiaryProvider,
    ImmichProvider,
    GooglePhotosProvider
]

# These are the words that are removed from the most common words list
# Should be in lowercase
COMMON_WORDS_FOR_USER_STATS = {
    'i',
    'added',
    'media',
    'file',
    'to',
    'is',
    'and',
    'in',
    'this',
    'for',
    'can',
    'was',
    'but',
    'not',
    'am',
    'it',
    'we',
    'my',
    'us',
    'the',
    'so',
    'you',
    'with',
    'are',
    'he',
    'have',
    'will',
    'do',
    'of',
    'if',
    'that',
    'on',
    'or',
    'from',
    'they',
    'at',
    'as',
    'liked',
    'message',
    'reacted',
    'your'
}
