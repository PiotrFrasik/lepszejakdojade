"""Translated fields of the ticket catalogue (django-modeltranslation, decision 7)."""

from modeltranslation.translator import TranslationOptions, register

from .models import Ticket


@register(Ticket)
class TicketTranslationOptions(TranslationOptions):
    fields = ("name", "description")
