from django.contrib import admin
from .models import CalculationRun, CashFlow, Entity, EntityConfiguration, PortfolioContract, LiquidityAssumptionSet, LiquidityAssumption, ProductCatalogueItem, RegulatorySourcePosition, RegulatorySnapshot, LcrStressConfiguration, LcrStressRun

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
    list_display = ['classification','product_group','product_type','cash_flow_treatment','general_ledger','is_temporary_gl','active']
    list_filter = ['classification','cash_flow_treatment','is_temporary_gl','active']
    search_fields = ['product_group','product_type','general_ledger']

@admin.register(RegulatorySourcePosition)
class RegulatorySourcePositionAdmin(admin.ModelAdmin):
    list_display = ['external_id','entity','lcr_category','lcr_direction','currency','balance','lcr_factor','hqla_level']
    list_filter = ['entity','lcr_direction','hqla_level','currency']
    search_fields = ['external_id','gl_code','product_group','product_type']

@admin.register(RegulatorySnapshot)
class RegulatorySnapshotAdmin(admin.ModelAdmin):
    list_display = ['entity','as_of_date','source','is_mock','created']
    list_filter = ['entity','is_mock']
    search_fields = ['entity__slug','source']
    readonly_fields = ['created']

admin.site.register(LcrStressConfiguration)
@admin.register(LcrStressRun)
class LcrStressRunAdmin(admin.ModelAdmin):
    list_display=['id','entity','as_of_date','created']
    readonly_fields=['entity','as_of_date','configuration','results','created']
