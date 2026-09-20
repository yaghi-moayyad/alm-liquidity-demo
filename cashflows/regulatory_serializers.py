from rest_framework import serializers
from .models import RegulatoryConfiguration, RegulatoryMapping, RegulatoryCalculation, RegulatoryContribution

class RegulatoryConfigurationSerializer(serializers.ModelSerializer):
    def validate_lcr_inflow_cap(self,value):
        if value < 0 or value > 1: raise serializers.ValidationError('LCR inflow cap must be between 0 and 1.')
        return value
    def validate_fx_to_reporting(self,value):
        if not isinstance(value,dict) or not value: raise serializers.ValidationError('Provide at least the reporting-currency FX rate.')
        try:
            if any(float(v) <= 0 for v in value.values()): raise ValueError
        except (TypeError,ValueError): raise serializers.ValidationError('FX rates must be positive numeric values.')
        return {str(k).upper():str(v) for k,v in value.items()}
    class Meta:
        model=RegulatoryConfiguration
        fields=['reporting_currency','fx_to_reporting','lcr_inflow_cap','methodology_name','methodology_version','updated']
        read_only_fields=['updated']

class RegulatoryMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model=RegulatoryMapping
        fields=['id','source_product','liquidity_group','liquidity_product','title','lcr_treatment','nsfr_treatment','source','active','updated']
        read_only_fields=['id','updated']

class RegulatoryCalculationSerializer(serializers.ModelSerializer):
    entity=serializers.CharField(source='entity.slug',read_only=True)
    class Meta:
        model=RegulatoryCalculation
        fields=['id','entity','as_of_date','created','engine_version','methodology_version','status','lcr_result','nsfr_result','controls','warnings']

class RegulatoryContributionSerializer(serializers.ModelSerializer):
    class Meta:
        model=RegulatoryContribution
        exclude=['id','calculation']
