from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins,viewsets
from rest_framework.permissions import BasePermission,SAFE_METHODS
from rest_framework.decorators import action,api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError,APIException
from drf_spectacular.utils import extend_schema,OpenApiTypes
from .models import Entity,EntityConfiguration,PortfolioContract
from .serializers import EntitySerializer,PortfolioInputSerializer,PortfolioResponseSerializer,RunInputSerializer,ValidationResponseSerializer,SessionSerializer,EntitySettingsSerializer
from .engine import DEFAULT_BUCKETS,calculate
from .services import hydrate_run_payload

class StaffWritePermission(BasePermission):
    def has_permission(self,request,view):
        return bool(request.user and request.user.is_authenticated and (request.method in SAFE_METHODS or request.user.is_staff))

class RevisionConflict(APIException):
    status_code=409
    default_detail='This portfolio was changed by another session. Reload it before saving again.'

class EntityViewSet(mixins.ListModelMixin,mixins.RetrieveModelMixin,mixins.CreateModelMixin,viewsets.GenericViewSet):
    permission_classes=[StaffWritePermission]
    serializer_class=EntitySerializer
    lookup_field='slug'
    queryset=Entity.objects.select_related('configuration').annotate(contract_count=Count('portfolio_contracts')).all()

    @transaction.atomic
    def perform_create(self,serializer):
        entity=serializer.save()
        entity.contract_count=0
        EntityConfiguration.objects.create(entity=entity,as_of_date=timezone.now().date(),bucket_days=DEFAULT_BUCKETS)

    @extend_schema(methods=['GET'],responses=PortfolioResponseSerializer)
    @extend_schema(methods=['PUT'],request=PortfolioInputSerializer,responses=PortfolioResponseSerializer)
    @action(detail=True,methods=['get','put'])
    def portfolio(self,request,slug=None):
        entity=self.get_object()
        if request.method=='PUT':
            serializer=PortfolioInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            values=serializer.validated_data
            if values['entity']!=entity.slug: raise ValidationError({'entity':'Request entity must match this portfolio.'})
            with transaction.atomic():
                config=EntityConfiguration.objects.select_for_update().get(entity=entity)
                if config.revision!=values['expected_revision']: raise RevisionConflict()
                # A conditional update also protects optimistic locking under SQLite.
                updated=EntityConfiguration.objects.filter(pk=config.pk,revision=values['expected_revision']).update(
                    as_of_date=values['as_of_date'],bucket_days=values['bucket_days'],revision=config.revision+1,updated=timezone.now())
                if not updated: raise RevisionConflict()
                entity.portfolio_contracts.all().delete()
                PortfolioContract.objects.bulk_create([PortfolioContract(entity=entity,external_id=c['contract_id'],terms=c) for c in values['contracts']],batch_size=500)
        config=EntityConfiguration.objects.get(entity=entity)
        data={'entity':EntitySerializer(self.get_queryset().get(pk=entity.pk)).data,'contracts':list(entity.portfolio_contracts.values_list('terms',flat=True)),
              'as_of_date':config.as_of_date.isoformat(),'bucket_days':config.bucket_days,'revision':config.revision}
        return Response(data)

    @extend_schema(methods=['GET'],responses=EntitySettingsSerializer)
    @extend_schema(methods=['PUT'],request=EntitySettingsSerializer,responses=EntitySettingsSerializer)
    @action(detail=True,methods=['get','put'],url_path='settings',url_name='settings')
    def interest_settings(self,request,slug=None):
        entity=self.get_object()
        config=EntityConfiguration.objects.get(entity=entity)
        if request.method == 'PUT':
            serializer=EntitySettingsSerializer(config,data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(EntitySettingsSerializer(config).data)

@extend_schema(request=RunInputSerializer,responses=ValidationResponseSerializer)
@api_view(['POST'])
def validate_portfolio(request):
    serializer=RunInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result=calculate(hydrate_run_payload(serializer.validated_data))
    return Response({k:result[k] for k in ('accepted_count','rejected_count','cashflow_count','exceptions','controls','undated')})

@extend_schema(responses=SessionSerializer)
@api_view(['GET'])
def session_info(request):
    return Response({'username':request.user.username,'is_staff':request.user.is_staff})
