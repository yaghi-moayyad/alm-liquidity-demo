from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins,viewsets
from rest_framework.permissions import BasePermission,SAFE_METHODS
from rest_framework.decorators import action,api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError,APIException
from drf_spectacular.utils import extend_schema,OpenApiTypes
from .models import Entity,EntityConfiguration,PortfolioContract,LiquidityAssumptionSet,LiquidityAssumption
from .serializers import EntitySerializer,PortfolioInputSerializer,PortfolioResponseSerializer,RunInputSerializer,ValidationResponseSerializer,SessionSerializer,EntitySettingsSerializer,LiquidityAssumptionSetSerializer,LiquidityAssumptionSerializer
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

    def _assumption_set(self, entity):
        return LiquidityAssumptionSet.objects.prefetch_related('rules').filter(entity=entity,status='active').first()

    @extend_schema(methods=['GET'],responses=LiquidityAssumptionSetSerializer)
    @extend_schema(methods=['POST'],request=LiquidityAssumptionSerializer,responses=LiquidityAssumptionSetSerializer)
    @action(detail=True,methods=['get','post'],url_path='assumptions')
    def assumptions(self,request,slug=None):
        entity=self.get_object(); assumption_set=self._assumption_set(entity)
        if not assumption_set: raise ValidationError('No active behavioural assumption set is configured for this entity.')
        if request.method=='POST':
            serializer=LiquidityAssumptionSerializer(data=request.data); serializer.is_valid(raise_exception=True)
            serializer.save(assumption_set=assumption_set)
            assumption_set.version += 1; assumption_set.save(update_fields=['version','updated'])
        return Response(LiquidityAssumptionSetSerializer(self._assumption_set(entity)).data)

    @extend_schema(methods=['PATCH'],request=LiquidityAssumptionSerializer,responses=LiquidityAssumptionSetSerializer)
    @action(detail=True,methods=['patch','delete'],url_path=r'assumptions/(?P<rule_id>[^/.]+)')
    def assumption_detail(self,request,slug=None,rule_id=None):
        entity=self.get_object(); assumption_set=self._assumption_set(entity)
        rule=LiquidityAssumption.objects.filter(assumption_set=assumption_set,pk=rule_id).first()
        if not rule: raise ValidationError({'rule_id':'Assumption was not found in this entity.'})
        if request.method=='DELETE': rule.delete()
        else:
            serializer=LiquidityAssumptionSerializer(rule,data=request.data,partial=True); serializer.is_valid(raise_exception=True); serializer.save()
        assumption_set.version += 1; assumption_set.save(update_fields=['version','updated'])
        return Response(LiquidityAssumptionSetSerializer(self._assumption_set(entity)).data)

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
