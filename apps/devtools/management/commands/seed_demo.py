import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.devtools import seeding

User = get_user_model()


class Command(BaseCommand):
    help = "Seed realistic demo data to try the frontend. Development only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete what was seeded and create it again."
        )
        parser.add_argument(
            "--member",
            metavar="EMAIL",
            help="Also make this existing user an admin of both demo businesses.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs in development (DEBUG must be on).")
        password = os.environ.get("SEED_DEMO_PASSWORD")
        if not password:
            raise CommandError(
                "Define SEED_DEMO_PASSWORD (a development password, not a real one) to run seed_demo."
            )
        member = None
        if options["member"]:
            member = User.objects.filter(email__iexact=options["member"]).first()
            if member is None:
                raise CommandError(f"There is no user {options['member']} to add as a member.")
        with transaction.atomic():
            if options["reset"]:
                seeding.reset_demo()
            if seeding.already_seeded():
                self.stdout.write(
                    "Demo data already exists, nothing was created. Use --reset to create it again."
                )
            else:
                acme, rival = seeding.seed_businesses_and_users(password)
                accounts = seeding.seed_accounts(acme, rival)
                seeding.seed_conversations(accounts, timezone.now())
            if member:
                seeding.add_admin(member)
        self.stdout.write(seeding.summary())
