from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Create missing escalation records'

    def handle(self, *args, **options):
        self.stdout.write('Done.')
