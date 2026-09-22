from copy import deepcopy
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import HttpResponse
from rest_framework import mixins,viewsets
from rest_framework.permissions import BasePermission,SAFE_METHODS
from rest_framework.decorators import action,api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError,APIException
from drf_spectacular.utils import extend_schema,OpenApiTypes
from .models import Entity,EntityConfiguration,PortfolioContract,LiquidityAssumptionSet,LiquidityAssumption,ProductCatalogueItem,RegulatorySnapshot,LcrStressConfiguration,LcrStressRun
from .serializers import EntitySerializer,PortfolioInputSerializer,PortfolioResponseSerializer,PortfolioContractQuerySerializer,RunInputSerializer,ValidationResponseSerializer,SessionSerializer,EntitySettingsSerializer,CalculationDefaultsSerializer,LiquidityAssumptionSetSerializer,LiquidityAssumptionSerializer,ProductCatalogueChoiceSerializer,ProductTreatmentSerializer
from .engine import DEFAULT_BUCKETS,calculate
from .services import hydrate_run_payload, preflight_saved_portfolio
from .regulatory import ncr_report,regulatory_report,regulatory_series,regulatory_drivers,regulatory_movement_history,regulatory_driver_detail
from .regulatory_export import lcr_xlsx,nsfr_xlsx
from .lcr_stress import default_configuration,normalise,calculate as calculate_lcr_stress,xlsx as lcr_stress_xlsx,DEFAULT_TOP,DEFAULTS

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
        # Bank portfolios are never loaded into the calculation browser.  The
        # summary endpoint is intentionally lightweight and exposes only safe
        # aggregate facts needed to submit a server-side run.
        if request.query_params.get('summary') in ('1','true','yes'):
            currencies=set(); products=set(); missing_maturity=0
            for terms in entity.portfolio_contracts.values_list('terms',flat=True).iterator(chunk_size=5_000):
                currencies.add(str(terms.get('currency') or '').upper())
                products.add(str(terms.get('product') or ''))
                if not str(terms.get('maturity') or '').strip(): missing_maturity += 1
            return Response({'entity':EntitySerializer(self.get_queryset().get(pk=entity.pk)).data,
                'as_of_date':config.as_of_date.isoformat(),'bucket_days':config.bucket_days,'revision':config.revision,
                'contract_count':entity.portfolio_contracts.count(),'currencies':sorted(item for item in currencies if item),
                'products':sorted(item for item in products if item),
                'product_count':len(products - {''}),'missing_maturity_count':missing_maturity})
        data={'entity':EntitySerializer(self.get_queryset().get(pk=entity.pk)).data,'contracts':list(entity.portfolio_contracts.values_list('terms',flat=True)),
              'as_of_date':config.as_of_date.isoformat(),'bucket_days':config.bucket_days,'revision':config.revision}
        return Response(data)

    @extend_schema(methods=['GET'],responses=OpenApiTypes.OBJECT)
    @action(detail=True,methods=['get'],url_path='portfolio-contracts')
    def portfolio_contracts(self,request,slug=None):
        """Page through a bank portfolio without copying all terms to React."""
        entity=self.get_object()
        filters=PortfolioContractQuerySerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values=filters.validated_data
        contracts=PortfolioContract.objects.filter(entity=entity).order_by('external_id')
        currency=values.get('currency')
        product=values.get('product')
        query=values.get('q','').strip()
        if currency:
            contracts=contracts.filter(terms__currency=currency)
        if product:
            contracts=contracts.filter(terms__product=product)
        if query:
            contracts=contracts.filter(
                Q(external_id__icontains=query) |
                Q(terms__liquidity_product__icontains=query) |
                Q(terms__liquidity_group__icontains=query)
            )
        total=contracts.count()
        offset,limit=values['offset'],values['limit']
        return Response({'total':total,'offset':offset,'limit':limit,
            'contracts':list(contracts.values_list('terms',flat=True)[offset:offset+limit])})

    @extend_schema(methods=['GET'],responses=EntitySettingsSerializer)
    @extend_schema(methods=['PUT'],request=EntitySettingsSerializer,responses=EntitySettingsSerializer)
    @action(detail=True,methods=['get','put'],url_path='settings',url_name='settings')
    def interest_settings(self,request,slug=None):
        entity=self.get_object()
        config=EntityConfiguration.objects.get(entity=entity)
        if request.method == 'PUT':
            serializer=EntitySettingsSerializer(config,data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(revision=config.revision+1)
        return Response(EntitySettingsSerializer(config).data)

    @extend_schema(methods=['PUT'],request=CalculationDefaultsSerializer,responses=CalculationDefaultsSerializer)
    @action(detail=True,methods=['put'],url_path='calculation-defaults')
    def calculation_defaults(self,request,slug=None):
        """Persist calculation date/buckets without shipping a portfolio to the client."""
        entity=self.get_object()
        with transaction.atomic():
            config=EntityConfiguration.objects.select_for_update().get(entity=entity)
            serializer=CalculationDefaultsSerializer(config,data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(revision=config.revision+1)
        return Response(CalculationDefaultsSerializer(config).data)

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

    @action(detail=True,methods=['get'],url_path='regulatory-driver-detail')
    def regulatory_driver_detail(self,request,slug=None):
        report_type=request.query_params.get('report_type','lcr');as_of=self._report_date(request);detail_key=request.query_params.get('detail_key','')
        allowed={'lcr':('hqla','net_cash_outflows'),'nsfr':('asf','rsf')}
        if report_type not in allowed: raise ValidationError({'report_type':'Choose lcr or nsfr.'})
        if detail_key not in allowed[report_type]: raise ValidationError({'detail_key':f'Choose one of: {", ".join(allowed[report_type])}.'})
        if not as_of: raise ValidationError({'as_of':'Choose a month-end reporting date.'})
        try:
            return Response(regulatory_driver_detail(self.get_object(),report_type,as_of,detail_key))
        except ValueError as error:
            raise ValidationError({'detail_key':str(error)})

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

    def _stress_config(self,entity):
        config,created=LcrStressConfiguration.objects.get_or_create(entity=entity,defaults={'configuration':default_configuration(),'top_depositor_amounts':DEFAULT_TOP})
        if created or not config.configuration:
            config.configuration=normalise(config.configuration);config.save()
        return config

    @action(detail=True,methods=['get','put'],url_path='lcr-stress-config')
    def lcr_stress_config(self,request,slug=None):
        config=self._stress_config(self.get_object())
        if request.method=='PUT':
            payload=request.data if isinstance(request.data,dict) else {}
            try:
                config.configuration=normalise(payload.get('configuration'))
                config.top_depositor_amounts=payload.get('top_depositor_amounts') or DEFAULT_TOP
            except Exception as error: raise ValidationError({'configuration':str(error)})
            config.save()
        return Response({'configuration':config.configuration,'top_depositor_amounts':config.top_depositor_amounts,'updated':config.updated})

    @action(detail=True,methods=['post'],url_path='lcr-stress-config/restore-default')
    def lcr_stress_restore_default(self,request,slug=None):
        """Restore one protected Central Bank scenario without changing other settings."""
        scenario_id=request.data.get('scenario_id')
        factory=next((item for item in DEFAULTS if item['id']==scenario_id),None)
        if not factory: raise ValidationError({'scenario_id':'Choose a shipped Central Bank scenario.'})
        config=self._stress_config(self.get_object())
        replacement=deepcopy(factory);found=False;updated=[]
        for scenario in config.configuration.get('scenarios',[]):
            if scenario.get('id')==scenario_id:
                updated.append(replacement);found=True
            else: updated.append(scenario)
        if not found: updated.append(replacement)
        config.configuration={**config.configuration,'scenarios':updated};config.save()
        return Response({'configuration':config.configuration,'top_depositor_amounts':config.top_depositor_amounts,'updated':config.updated})

    @action(detail=True,methods=['get'],url_path='lcr-stress-preview')
    def lcr_stress_preview(self,request,slug=None):
        """Calculate the selected snapshot without creating a permanent stress-test run."""
        entity=self.get_object();as_of=self._report_date(request)
        snapshot=RegulatorySnapshot.objects.filter(entity=entity,as_of_date=as_of).first() if as_of else RegulatorySnapshot.objects.filter(entity=entity).first()
        if not snapshot: raise ValidationError({'as_of':'No regulatory source snapshot is available.'})
        config=self._stress_config(entity)
        results=calculate_lcr_stress(entity,snapshot.as_of_date,snapshot.source_data.get('lcr_positions',[]),config.configuration,config.top_depositor_amounts)
        return Response({'as_of_date':snapshot.as_of_date,'configuration':config.configuration,'results':results})

    @action(detail=True,methods=['get','post'],url_path='lcr-stress-runs')
    def lcr_stress_runs(self,request,slug=None):
        entity=self.get_object()
        if request.method=='GET':
            return Response({'runs':[{'id':run.id,'as_of_date':run.as_of_date,'created':run.created,'baseline_lcr':run.results.get('baseline',{}).get('lcr'),'scenario_count':len(run.results.get('results',[]))} for run in LcrStressRun.objects.filter(entity=entity)[:25]]})
        as_of=self._report_date(request)
        snapshot=RegulatorySnapshot.objects.filter(entity=entity,as_of_date=as_of).first() if as_of else RegulatorySnapshot.objects.filter(entity=entity).first()
        if not snapshot: raise ValidationError({'as_of':'No regulatory source snapshot is available.'})
        config=self._stress_config(entity);results=calculate_lcr_stress(entity,snapshot.as_of_date,snapshot.source_data.get('lcr_positions',[]),config.configuration,config.top_depositor_amounts)
        run=LcrStressRun.objects.create(entity=entity,as_of_date=snapshot.as_of_date,configuration={'configuration':config.configuration,'top_depositor_amounts':config.top_depositor_amounts},results=results)
        return Response({'id':run.id,'as_of_date':run.as_of_date,'created':run.created,'results':run.results},status=201)

    @action(detail=True,methods=['get'],url_path=r'lcr-stress-runs/(?P<run_id>[^/.]+)')
    def lcr_stress_run(self,request,slug=None,run_id=None):
        run=LcrStressRun.objects.filter(entity=self.get_object(),pk=run_id).first()
        if not run: raise ValidationError({'run_id':'Stress-test run was not found.'})
        return Response({'id':run.id,'as_of_date':run.as_of_date,'created':run.created,'configuration':run.configuration,'results':run.results})

    @action(detail=True,methods=['get'],url_path=r'lcr-stress-runs/(?P<run_id>[^/.]+)/export')
    def lcr_stress_export(self,request,slug=None,run_id=None):
        run=LcrStressRun.objects.filter(entity=self.get_object(),pk=run_id).first()
        if not run: raise ValidationError({'run_id':'Stress-test run was not found.'})
        entity=self.get_object()
        response=HttpResponse(lcr_stress_xlsx({'results':run.results},entity_name=entity.name,as_of_date=run.as_of_date),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition']=f'attachment; filename="{entity.slug}_lcr_stress_{run.as_of_date}.xlsx"'
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
    if serializer.validated_data.get('use_saved_portfolio'):
        result=preflight_saved_portfolio(serializer.validated_data)
    else:
        result=calculate(hydrate_run_payload(serializer.validated_data))
    response={k:result[k] for k in ('accepted_count','rejected_count','cashflow_count','exceptions','controls','undated')}
    # Manual/sample calculations have no imported portfolio to analyse. Keep
    # the API shape stable so the React readiness screen receives an empty set.
    response['readiness_groups']=result.get('readiness_groups',[])
    return Response(response)

@extend_schema(responses=SessionSerializer)
@api_view(['GET'])
def session_info(request):
    return Response({'username':request.user.username,'is_staff':request.user.is_staff})
