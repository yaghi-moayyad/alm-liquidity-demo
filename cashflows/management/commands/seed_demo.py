import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from cashflows.models import Entity,CalculationRun
from cashflows.services import submit_run,execute_run

class Command(BaseCommand):
    help='Create one initial Jordan-Mock result for a user, without overwriting the saved portfolio.'
    def add_arguments(self,parser):
        parser.add_argument('--username')
        parser.add_argument('--replace',action='store_true',help='Replace an existing user-owned Jordan-Mock baseline run.')
        parser.add_argument('--create-user',action='store_true',help='Create the named local demo administrator when it does not exist.')
        parser.add_argument('--password',help='Password only when --create-user is used. Defaults to DEMO_PASSWORD.')
    def handle(self,*args,**options):
        users=get_user_model()
        user=(users.objects.filter(username=options['username']).first() if options['username'] else users.objects.filter(is_superuser=True).order_by('id').first())
        if user is None and options['create_user']:
            username=options['username'] or 'demo'
            password=options['password'] or os.environ.get('DEMO_PASSWORD')
            if not password:
                raise CommandError('DEMO_PASSWORD is required when creating a demo user.')
            user=users.objects.create_superuser(username=username,password=password,email='')
            self.stdout.write(self.style.WARNING(f'Created demo administrator {username}. Use the password supplied to this command or DEMO_PASSWORD.'))
        elif user is not None and options['create_user']:
            # This intentional demo account must remain a real full administrator
            # if a previous deployment created it with lesser privileges.
            password=options['password']
            changed=[]
            if not user.is_staff: user.is_staff=True; changed.append('is_staff')
            if not user.is_superuser: user.is_superuser=True; changed.append('is_superuser')
            if password: user.set_password(password); changed.append('password')
            if changed: user.save(update_fields=list(dict.fromkeys(changed)))
        if user is None: raise CommandError('Create a user first, or supply --username with --create-user.')
        entity=Entity.objects.get(slug='jordan-mock')
        existing=CalculationRun.objects.filter(owner=user,entity_ref=entity)
        if existing.exists() and not options['replace']:
            self.stdout.write('Existing Jordan-Mock runs preserved.');return
        if options['replace']:
            existing.delete()
        config=entity.configuration
        payload={'entity':entity.slug,'as_of_date':config.as_of_date.isoformat(),'bucket_days':config.bucket_days,'contracts':list(entity.portfolio_contracts.values_list('terms',flat=True))}
        run,_=submit_run(user,payload)
        execute_run(run.pk)
        self.stdout.write(f'Jordan-Mock ready: {len(payload["contracts"])} saved contracts and a baseline run for {user.username}.')
