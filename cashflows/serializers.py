from collections.abc import Mapping
from decimal import Decimal
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .engine import validate_config, MAX_CONTRACTS, DEFAULT_BUCKETS, PRECISION
from .models import CalculationRun, CashFlow, Entity, EntityConfiguration

class RunInputSerializer(serializers.Serializer):
    entity = serializers.SlugField(max_length=64)
    as_of_date = serializers.DateField()
    bucket_days = serializers.ListField(child=serializers.IntegerField(min_value=1,max_value=36500),default=list(DEFAULT_BUCKETS),min_length=1,max_length=30)
    contracts = serializers.ListField(child=serializers.JSONField(),min_length=1,max_length=MAX_CONTRACTS,
        help_text='Contract objects. Individual invalid/unsupported contracts appear in run exceptions; see sample endpoint and API guide for fields.')

    def to_internal_value(self, data):
        if isinstance(data,Mapping):
            extra=set(data)-set(self.fields)
            if extra: raise serializers.ValidationError({'unknown_fields':sorted(extra)})
            # Validate raw boundaries too: do not silently coerce 1.1, true or strings into days.
            if 'bucket_days' in data and (not isinstance(data['bucket_days'],list) or any(type(v) is not int for v in data['bucket_days'])):
                raise serializers.ValidationError({'bucket_days':'Use integer day boundaries only.'})
        return super().to_internal_value(data)

    def validate(self,attrs):
        if not Entity.objects.filter(slug=attrs['entity']).exists():
            raise serializers.ValidationError({'entity':'Select an existing entity.'})
        attrs['as_of_date']=attrs['as_of_date'].isoformat()
        try: validate_config(attrs)
        except (ValueError,TypeError) as exc: raise serializers.ValidationError(str(exc))
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
        fields=['as_of_date','interest_projection','forward_curve','updated']
        read_only_fields=['as_of_date','updated']
    def validate_interest_projection(self,value):
        if value not in ('constant','forward_curve'):
            raise serializers.ValidationError('Choose constant or forward_curve.')
        return value
    def validate(self,attrs):
        if attrs.get('interest_projection',self.instance.interest_projection if self.instance else 'constant') == 'forward_curve' and not attrs.get('forward_curve', self.instance.forward_curve if self.instance else []):
            raise serializers.ValidationError({'forward_curve':'Add at least one curve point before using the market forward curve.'})
        return attrs

class PortfolioInputSerializer(RunInputSerializer):
    expected_revision=serializers.IntegerField(min_value=1)
    def validate(self,attrs):
        revision=attrs.pop('expected_revision')
        attrs=super().validate(attrs)
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

class ValidationResponseSerializer(serializers.Serializer):
    accepted_count=serializers.IntegerField()
    rejected_count=serializers.IntegerField()
    cashflow_count=serializers.IntegerField()
    exceptions=serializers.ListField(child=serializers.JSONField())
    controls=serializers.ListField(child=serializers.JSONField())
    undated=serializers.ListField(child=serializers.JSONField())

class SessionSerializer(serializers.Serializer):
    username=serializers.CharField()
    is_staff=serializers.BooleanField()
