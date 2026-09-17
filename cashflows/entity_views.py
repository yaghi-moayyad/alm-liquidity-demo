from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import HttpResponse
from rest_framework import mixins,viewsets
from rest_framework.permissions import BasePermission,SAFE_METHODS
from rest_framework.decorators import action,api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError,APIException
from drf_spectacular.utils import extend_schema,OpenApiTypes
from .models import Entity,EntityConfiguration,PortfolioContract,LiquidityAssumptionSet,LiquidityAssumption,ProductCatalogueItem,RegulatorySnapshot
from .serializers import EntitySerializer,PortfolioInputSerializer,PortfolioResponseSerializer,RunInputSerializer,ValidationResponseSerializer,SessionSerializer,EntitySettingsSerializer,LiquidityAssumptionSetSerializer,LiquidityAssumptionSerializer,ProductCatalogueChoiceSerializer,ProductTreatmentSerializer
from .engine import DEFAULT_BUCKETS,calculate
from .services import hydrate_run_payload
from .regulatory import ncr_report,regulatory_report,regulatory_series,regulatory_drivers,regulatory_movement_history
from .regulatory_export import lcr_xlsx,nsfr_xlsx

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

    @extend_schema(methods=['GET'],responses=ProductCatalogueChoiceSerializer(many=True))
    @action(detail=True,methods=['get'],url_path='product-catalogue')
    def product_catalogue(self,request,slug=None):
        # GL mappings remain protected in Django admin. The client needs only
        # safe, controlled choices for the assumption editor.
        entity=self.get_object()
        items=ProductCatalogueItem.objects.filter(entity=entity,active=True)
        return Response(ProductCatalogueChoiceSerializer(items,many=True).data)

    @extend_schema(methods=['PATCH'],request=ProductTreatmentSerializer,responses=ProductCatalogueChoiceSerializer)
    @action(detail=True,methods=['patch'],url_path=r'product-catalogue/(?P<item_id>[^/.]+)')
    def product_catalogue_detail(self,request,slug=None,item_id=None):
        entity=self.get_object()
        item=ProductCatalogueItem.objects.filter(entity=entity,pk=item_id).first()
        if not item: raise ValidationError({'item_id':'Product catalogue item was not found for this entity.'})
        serializer=ProductTreatmentSerializer(item,data=request.data,partial=True); serializer.is_valid(raise_exception=True); serializer.save()
        return Response(ProductCatalogueChoiceSerializer(item).data)

    @action(detail=True,methods=['get'],url_path='ncr-report')
    def ncr_report(self,request,slug=None):
        return Response(ncr_report(self.get_object()))

    def _report_date(self, request):
        raw=request.query_params.get('as_of')
        if not raw: return None
        value=parse_date(raw)
        if not value: raise ValidationError({'as_of':'Use a date in YYYY-MM-DD format.'})
        return value

    @action(detail=True,methods=['get'],url_path='lcr-report')
    def lcr_report(self,request,slug=None):
        return Response(regulatory_report(self.get_object(),'lcr',self._report_date(request)))

    @action(detail=True,methods=['get'],url_path='nsfr-report')
    def nsfr_report(self,request,slug=None):
        return Response(regulatory_report(self.get_object(),'nsfr',self._report_date(request)))

    @action(detail=True,methods=['get'],url_path='regulatory-series')
    def regulatory_series(self,request,slug=None):
        report_type=request.query_params.get('report_type','lcr')
        if report_type not in ('lcr','nsfr'): raise ValidationError({'report_type':'Choose lcr or nsfr.'})
        return Response({'report_type':report_type,'points':regulatory_series(self.get_object(),report_type)})

    @action(detail=True,methods=['get'],url_path='regulatory-drivers')
    def regulatory_drivers(self,request,slug=None):
        report_type=request.query_params.get('report_type','lcr');as_of=self._report_date(request)
        if report_type not in ('lcr','nsfr'): raise ValidationError({'report_type':'Choose lcr or nsfr.'})
        if not as_of:
            snapshot=RegulatorySnapshot.objects.filter(entity=self.get_object()).first()
            if not snapshot: raise ValidationError({'as_of':'No regulatory snapshot is available.'})
            as_of=snapshot.as_of_date
        return Response(regulatory_drivers(self.get_object(),report_type,as_of))

    @action(detail=True,methods=['get'],url_path='regulatory-movement-history')
    def regulatory_movement_history(self,request,slug=None):
        report_type=request.query_params.get('report_type','lcr')
        if report_type not in ('lcr','nsfr'): raise ValidationError({'report_type':'Choose lcr or nsfr.'})
        return Response({'report_type':report_type,'movements':regulatory_movement_history(self.get_object(),report_type)})

    @action(detail=True,methods=['get'],url_path='regulatory-export')
    def regulatory_export(self,request,slug=None):
        report_type=request.query_params.get('report_type','lcr');entity=self.get_object();as_of=self._report_date(request)
        if report_type not in ('lcr','nsfr'): raise ValidationError({'report_type':'Choose lcr or nsfr.'})
        snapshot=RegulatorySnapshot.objects.filter(entity=entity,as_of_date=as_of).first() if as_of else RegulatorySnapshot.objects.filter(entity=entity).first()
        if not snapshot: raise ValidationError('No regulatory snapshot is available for export.')
        content=lcr_xlsx(regulatory_report(entity,'lcr',snapshot.as_of_date),snapshot.source_data.get('lcr_positions',[])) if report_type=='lcr' else nsfr_xlsx(snapshot.source_data.get('nsfr_lines',[]))
        response=HttpResponse(content,content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition']=f'attachment; filename="{entity.slug}_{report_type}_{snapshot.as_of_date}.xlsx"'
        return response

    def _assumption_set(self, entity):
        return LiquidityAssumptionSet.objects.prefetch_related('rules').filter(entity=entity,status='active').first()

    def _validate_catalogue_choice(self, entity, values, rule=None):
        group=values.get('product_group',rule.product_group if rule else '')
        product=values.get('product_type',rule.product_type if rule else '')
        candidates=ProductCatalogueItem.objects.filter(entity=entity,active=True,product_group=group)
        if not candidates.exists(): raise ValidationError({'product_group':'Choose a report group from the product catalogue.'})
        if product not in ('ALL','') and not candidates.filter(product_type=product).exists():
            raise ValidationError({'product_type':'Choose a product type from the selected report group.'})

    @extend_schema(methods=['GET'],responses=LiquidityAssumptionSetSerializer)
    @extend_schema(methods=['POST'],request=LiquidityAssumptionSerializer,responses=LiquidityAssumptionSetSerializer)
    @action(detail=True,methods=['get','post'],url_path='assumptions')
    def assumptions(self,request,slug=None):
        entity=self.get_object(); assumption_set=self._assumption_set(entity)
        if not assumption_set: raise ValidationError('No active behavioural assumption set is configured for this entity.')
        if request.method=='POST':
            serializer=LiquidityAssumptionSerializer(data=request.data); serializer.is_valid(raise_exception=True)
            self._validate_catalogue_choice(entity,serializer.validated_data)
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
            serializer=LiquidityAssumptionSerializer(rule,data=request.data,partial=True); serializer.is_valid(raise_exception=True)
            self._validate_catalogue_choice(entity,serializer.validated_data,rule); serializer.save()
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
