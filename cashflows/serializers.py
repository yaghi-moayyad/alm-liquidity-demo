from collections.abc import Mapping
from decimal import Decimal
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .engine import validate_config, MAX_CONTRACTS, DEFAULT_BUCKETS, PRECISION
from .models import CalculationRun, CashFlow, Entity, EntityConfiguration, PortfolioContract, RunContract, LiquidityAssumption, LiquidityAssumptionSet, ProductCatalogueItem

class RunInputSerializer(serializers.Serializer):
    entity = serializers.SlugField(max_length=64)
    as_of_date = serializers.DateField()
    bucket_days = serializers.ListField(child=serializers.IntegerField(min_value=1,max_value=36500),default=list(DEFAULT_BUCKETS),min_length=1,max_length=30)
    contracts = serializers.ListField(child=serializers.JSONField(),min_length=1,max_length=MAX_CONTRACTS,required=False,
        help_text='Contract objects. Individual invalid/unsupported contracts appear in run exceptions; see sample endpoint and API guide for fields.')
    use_saved_portfolio = serializers.BooleanField(default=False, required=False,
        help_text='Retrieve the selected entity portfolio on the server. Required for bank-scale calculations.')
    calculation_basis = serializers.ChoiceField(choices=['contractual','behavioral'], default='contractual', required=False)
    data_readiness_resolutions = serializers.ListField(child=serializers.JSONField(), required=False, default=list,
        help_text='Run-only, grouped resolutions for source-data exceptions. Source portfolio data is never changed.')

    def to_internal_value(self, data):
        if isinstance(data,Mapping):
            extra=set(data)-set(self.fields)
            if extra: raise serializers.ValidationError({'unknown_fields':sorted(extra)})
            # Validate raw boundaries too: do not silently coerce 1.1, true or strings into days.
            if 'bucket_days' in data and (not isinstance(data['bucket_days'],list) or any(type(v) is not int for v in data['bucket_days'])):
                raise serializers.ValidationError({'bucket_days':'Use integer day boundaries only.'})
        return super().to_internal_value(data)

    def validate(self,attrs):
        entity=Entity.objects.filter(slug=attrs['entity']).first()
        if not entity:
            raise serializers.ValidationError({'entity':'Select an existing entity.'})
        saved=attrs.get('use_saved_portfolio',False)
        if saved and attrs.get('contracts'):
            raise serializers.ValidationError({'contracts':'Do not send contracts when using the saved portfolio.'})
        if not saved and not attrs.get('contracts'):
            raise serializers.ValidationError({'contracts':'Provide contracts or select use_saved_portfolio.'})
        if saved and not PortfolioContract.objects.filter(entity=entity).exists():
            raise serializers.ValidationError({'portfolio':'The saved portfolio is empty.'})
        allowed_actions={'use_candidate_date','set_next_payment_date','derive_from_reporting_date','proxy_maturity','exclude'}
        for index,resolution in enumerate(attrs.get('data_readiness_resolutions',[]),start=1):
            if not isinstance(resolution,dict):
                raise serializers.ValidationError({'data_readiness_resolutions':f'Resolution {index} must be an object.'})
            unknown=set(resolution)-{'group_key','action','date','candidate_field'}
            if unknown or not isinstance(resolution.get('group_key'),str) or resolution.get('action') not in allowed_actions:
                raise serializers.ValidationError({'data_readiness_resolutions':f'Resolution {index} needs group_key and an approved action.'})
            if resolution.get('action') in {'set_next_payment_date','proxy_maturity'} and not resolution.get('date'):
                raise serializers.ValidationError({'data_readiness_resolutions':f'Resolution {index} needs a next-payment date.'})
            if resolution.get('action')=='use_candidate_date' and not resolution.get('candidate_field'):
                raise serializers.ValidationError({'data_readiness_resolutions':f'Resolution {index} needs a source date field.'})
        attrs['as_of_date']=attrs['as_of_date'].isoformat()
        try: validate_config(attrs)
        except (ValueError,TypeError) as exc:
            if not saved: raise serializers.ValidationError(str(exc))
            # The execution configuration is valid; the bank portfolio itself
            # is intentionally hydrated only on the server after validation.
            preview=dict(attrs)
            preview['contracts']=[{'contract_id':'server-portfolio-preview','product':'loan','currency':'JOD','principal':'1'}]
            try: validate_config(preview)
            except (ValueError,TypeError) as preview_error: raise serializers.ValidationError(str(preview_error))
        return attrs

class RunListSerializer(serializers.ModelSerializer):
    entity = serializers.CharField(source='entity_ref.slug',read_only=True)
    entity_name = serializers.CharField(source='entity_ref.name', read_only=True)
    is_mock = serializers.BooleanField(source='entity_ref.is_mock', read_only=True)
    class Meta:
        model=CalculationRun
        fields=['id','created','status','progress','error','as_of_date','entity','entity_name','is_mock','engine_version']

class RunDetailSerializer(RunListSerializer):
    result=serializers.JSONField(source='result_summary',read_only=True)
    class Meta(RunListSerializer.Meta):
        fields=RunListSerializer.Meta.fields+['started','finished','heartbeat','input_hash','result']

class RunAcceptedSerializer(serializers.Serializer):
    id=serializers.UUIDField()
    status=serializers.CharField()
    status_url=serializers.CharField()
    reused=serializers.BooleanField()

class HealthSerializer(serializers.Serializer):
    status=serializers.CharField()
    version=serializers.CharField()
    framework=serializers.CharField()

class CashFlowSerializer(serializers.ModelSerializer):
    class Meta:
        model=CashFlow
        exclude=['id','run','sequence']
    def to_representation(self,instance):
        data=super().to_representation(instance)
        for k in ['principal','interest','total','remaining_principal']:
            data[k]=str(Decimal(data[k]).quantize(PRECISION[data['currency']]))
        return data

class FlowPageSerializer(serializers.Serializer):
    total=serializers.IntegerField()
    offset=serializers.IntegerField()
    limit=serializers.IntegerField()
    cashflows=CashFlowSerializer(many=True)

class RunPageSerializer(serializers.Serializer):
    runs=RunListSerializer(many=True)

class FlowQuerySerializer(serializers.Serializer):
    offset=serializers.IntegerField(default=0,min_value=0)
    limit=serializers.IntegerField(default=200,min_value=1,max_value=1000)
    contract_id=serializers.CharField(required=False,max_length=64)
    currency=serializers.ChoiceField(required=False,choices=list(PRECISION))
    product=serializers.CharField(required=False,max_length=32)

class ContractSearchQuerySerializer(serializers.Serializer):
    q=serializers.CharField(min_length=2,max_length=64,trim_whitespace=True)
    limit=serializers.IntegerField(default=25,min_value=1,max_value=50)

class RunContractSerializer(serializers.ModelSerializer):
    class Meta:
        model=RunContract
        fields=['contract_id','product','currency','direction']

class ContractSearchResponseSerializer(serializers.Serializer):
    query=serializers.CharField()
    contracts=RunContractSerializer(many=True)


class EntitySerializer(serializers.ModelSerializer):
    contract_count = serializers.IntegerField(read_only=True)
    as_of_date = serializers.DateField(source='configuration.as_of_date',read_only=True)
    class Meta:
        model=Entity
        fields=['id','slug','name','country','base_currency','is_mock','contract_count','as_of_date']
    def validate_base_currency(self,value):
        if value not in PRECISION: raise serializers.ValidationError('Choose JOD, USD, EUR or GBP.')
        return value

class ForwardCurvePointSerializer(serializers.Serializer):
    currency=serializers.ChoiceField(choices=list(PRECISION))
    index=serializers.CharField(max_length=64)
    tenor_days=serializers.IntegerField(min_value=1,max_value=36500)
    rate=serializers.DecimalField(max_digits=8,decimal_places=6,min_value=Decimal('0'),max_value=Decimal('1'))

class EntitySettingsSerializer(serializers.ModelSerializer):
    forward_curve=ForwardCurvePointSerializer(many=True,required=False)
    class Meta:
        model=EntityConfiguration
        fields=['as_of_date','interest_projection','forward_curve','proxy_maturity_enabled','proxy_maturity_date','proxy_maturity_scope','updated']
        read_only_fields=['as_of_date','updated']
    def validate_interest_projection(self,value):
        if value not in ('constant','forward_curve'):
            raise serializers.ValidationError('Choose constant or forward_curve.')
        return value
    def validate(self,attrs):
        if attrs.get('interest_projection',self.instance.interest_projection if self.instance else 'constant') == 'forward_curve' and not attrs.get('forward_curve', self.instance.forward_curve if self.instance else []):
            raise serializers.ValidationError({'forward_curve':'Add at least one curve point before using the market forward curve.'})
        enabled=attrs.get('proxy_maturity_enabled',self.instance.proxy_maturity_enabled if self.instance else False)
        maturity=attrs.get('proxy_maturity_date',self.instance.proxy_maturity_date if self.instance else None)
        as_of=self.instance.as_of_date if self.instance else None
        if enabled and not maturity:
            raise serializers.ValidationError({'proxy_maturity_date':'Set a proxy maturity date before enabling the policy.'})
        if enabled and as_of and maturity <= as_of:
            raise serializers.ValidationError({'proxy_maturity_date':'Proxy maturity must be after the current reporting date.'})
        return attrs

class CalculationDefaultsSerializer(serializers.ModelSerializer):
    bucket_days=serializers.ListField(child=serializers.IntegerField(min_value=1,max_value=36500),min_length=1,max_length=30)
    class Meta:
        model=EntityConfiguration
        fields=['as_of_date','bucket_days','revision','updated']
        read_only_fields=['revision','updated']
    def validate_bucket_days(self,value):
        if value != sorted(set(value)):
            raise serializers.ValidationError('Use strictly increasing bucket boundaries.')
        return value

class LiquidityAssumptionSerializer(serializers.ModelSerializer):
    class Meta:
        model=LiquidityAssumption
        fields=['id','category','title','product_group','product_type','currency_scope','maturity_breakdown','value','enabled','sort_order','updated']
        read_only_fields=['id','updated']
    def validate(self,attrs):
        category=attrs.get('category',self.instance.category if self.instance else None)
        value=attrs.get('value',self.instance.value if self.instance else {})
        curve_categories={'deposit_runoff','term_deposit_early_withdrawal','loan_prepayment','facility_drawdown'}
        if category in curve_categories:
            points=value.get('curve') if isinstance(value,dict) else None
            if not isinstance(points,list) or not points:
                raise serializers.ValidationError({'value':'Add at least one cumulative curve point.'})
            previous=-1; days_seen=set()
            for point in points:
                try: days=int(point['days']); cumulative=Decimal(str(point['cumulative']))
                except (KeyError,TypeError,ValueError): raise serializers.ValidationError({'value':'Every curve point needs numeric days and cumulative percentage.'})
                if days < 1 or days in days_seen: raise serializers.ValidationError({'value':'Curve days must be positive and unique.'})
                if not Decimal('0') <= cumulative <= Decimal('1') or cumulative < previous:
                    raise serializers.ValidationError({'value':'Cumulative percentages must increase from 0% to 100%.'})
                days_seen.add(days); previous=cumulative
        elif category=='security_haircut':
            try: haircut=Decimal(str(value.get('haircut')))
            except (AttributeError,TypeError,ValueError): raise serializers.ValidationError({'value':'Enter a numeric haircut.'})
            if not Decimal('0') <= haircut <= Decimal('1'):
                raise serializers.ValidationError({'value':'Haircut must be between 0% and 100%.'})
        elif category=='rollover':
            try:
                rate=Decimal(str(value.get('rollover_rate'))); days=int(value.get('rollover_days'))
            except (AttributeError,TypeError,ValueError): raise serializers.ValidationError({'value':'Enter a rollover rate and whole-number renewal days.'})
            if not Decimal('0') <= rate <= Decimal('1') or not 1 <= days <= 36500:
                raise serializers.ValidationError({'value':'Rollover rate must be 0%–100% and renewal days 1–36500.'})
        return attrs

class LiquidityAssumptionSetSerializer(serializers.ModelSerializer):
    rules=LiquidityAssumptionSerializer(many=True,read_only=True)
    class Meta:
        model=LiquidityAssumptionSet
        fields=['id','name','version','effective_date','status','source','is_system','updated','rules']
        read_only_fields=['id','version','updated','is_system']

class ProductCatalogueChoiceSerializer(serializers.ModelSerializer):
    """The GL is intentionally excluded from the application-facing catalogue."""
    class Meta:
        model=ProductCatalogueItem
        fields=['id','classification','product_group','product_type','cash_flow_treatment','treatment_note']

class ProductTreatmentSerializer(serializers.ModelSerializer):
    class Meta:
        model=ProductCatalogueItem
        fields=['cash_flow_treatment','treatment_note']

class PortfolioInputSerializer(RunInputSerializer):
    expected_revision=serializers.IntegerField(min_value=1)
    def validate(self,attrs):
        revision=attrs.pop('expected_revision')
        attrs=super().validate(attrs)
        if attrs.get('use_saved_portfolio'):
            raise serializers.ValidationError({'use_saved_portfolio':'Portfolio updates must include an explicit contract list.'})
        ids=[]
        import re
        for contract in attrs['contracts']:
            if not isinstance(contract,dict) or not isinstance(contract.get('contract_id'),str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',contract['contract_id']):
                raise serializers.ValidationError('Every saved contract needs a valid contract_id.')
            ids.append(contract['contract_id'])
        if len(ids)!=len(set(ids)): raise serializers.ValidationError('Contract IDs must be unique within an entity.')
        attrs['expected_revision']=revision
        return attrs

class PortfolioResponseSerializer(serializers.Serializer):
    entity=EntitySerializer()
    contracts=serializers.ListField(child=serializers.JSONField())
    as_of_date=serializers.DateField()
    bucket_days=serializers.ListField(child=serializers.IntegerField())
    revision=serializers.IntegerField()


class PortfolioContractQuerySerializer(serializers.Serializer):
    """Bounded, indexed portfolio browsing for bank-scale entities."""
    q=serializers.CharField(required=False,max_length=64,trim_whitespace=True)
    currency=serializers.ChoiceField(required=False,choices=list(PRECISION))
    product=serializers.CharField(required=False,max_length=32)
    offset=serializers.IntegerField(default=0,min_value=0)
    limit=serializers.IntegerField(default=50,min_value=1,max_value=100)

class ValidationResponseSerializer(serializers.Serializer):
    accepted_count=serializers.IntegerField()
    rejected_count=serializers.IntegerField()
    cashflow_count=serializers.IntegerField()
    exceptions=serializers.ListField(child=serializers.JSONField())
    controls=serializers.ListField(child=serializers.JSONField())
    undated=serializers.ListField(child=serializers.JSONField())
    readiness_groups=serializers.ListField(child=serializers.JSONField(),required=False)

class SessionSerializer(serializers.Serializer):
    username=serializers.CharField()
    is_staff=serializers.BooleanField()
