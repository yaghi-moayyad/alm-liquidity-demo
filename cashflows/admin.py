from django.contrib import admin
from .models import CalculationRun, CashFlow, BehavioralCashFlow, Entity, EntityConfiguration, PortfolioContract, LiquidityAssumptionSet, LiquidityAssumption, ProductCatalogueItem, RegulatoryConfiguration, RegulatoryMapping, RegulatoryCalculation, RegulatoryContribution

@admin.register(CalculationRun)
class RunAdmin(admin.ModelAdmin):
    list_display = ['id','owner','as_of_date','status','progress','created']
    list_filter = ['status','entity']
    search_fields = ['id','owner__username']
    readonly_fields = [f.name for f in CalculationRun._meta.fields]
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return False

@admin.register(CashFlow)
class FlowAdmin(admin.ModelAdmin):
    list_display = ['contract_id','run','payment_date','currency','principal','interest']
    search_fields = ['contract_id']
    list_filter = ['currency','product']
    readonly_fields = [f.name for f in CashFlow._meta.fields]
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return False

admin.site.register(Entity)
admin.site.register(EntityConfiguration)
admin.site.register(PortfolioContract)

@admin.register(LiquidityAssumptionSet)
class LiquidityAssumptionSetAdmin(admin.ModelAdmin):
    list_display = ['name','entity','version','status','effective_date','updated']
    list_filter = ['status','entity']
    search_fields = ['name','entity__slug']

@admin.register(LiquidityAssumption)
class LiquidityAssumptionAdmin(admin.ModelAdmin):
    list_display = ['title','assumption_set','category','currency_scope','enabled','updated']
    list_filter = ['category','enabled','currency_scope']
    search_fields = ['title','product_group','product_type']

@admin.register(ProductCatalogueItem)
class ProductCatalogueItemAdmin(admin.ModelAdmin):
    list_display = ['classification','product_group','product_type','cashflow_treatment','general_ledger','is_temporary_gl','active']
    list_filter = ['classification','cashflow_treatment','is_temporary_gl','active']
    search_fields = ['product_group','product_type','general_ledger']

@admin.register(BehavioralCashFlow)
class BehavioralFlowAdmin(admin.ModelAdmin):
    list_display = ['contract_id','run','payment_date','currency','principal','behavioral_source','behavioral_rule_title']
    search_fields = ['contract_id','behavioral_rule_title']
    list_filter = ['currency','product','behavioral_source']
    readonly_fields = [f.name for f in BehavioralCashFlow._meta.fields]
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return False

admin.site.register(RegulatoryConfiguration)
admin.site.register(RegulatoryMapping)
admin.site.register(RegulatoryCalculation)
admin.site.register(RegulatoryContribution)
