import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q

class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=80)
    country = models.CharField(max_length=80, default='Jordan')
    base_currency = models.CharField(max_length=3, default='JOD')
    is_mock = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['name']
    def __str__(self): return self.name

class EntityConfiguration(models.Model):
    entity = models.OneToOneField(Entity, on_delete=models.CASCADE, related_name='configuration')
    as_of_date = models.DateField()
    bucket_days = models.JSONField(default=list)
    interest_projection = models.CharField(max_length=24, default='constant')
    forward_curve = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=1)
    updated = models.DateTimeField(auto_now=True)


class LiquidityAssumptionSet(models.Model):
    """A versioned, entity-scoped set of behavioural liquidity rules."""
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        DRAFT = 'draft', 'Draft'
        RETIRED = 'retired', 'Retired'

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name='assumption_sets')
    name = models.CharField(max_length=120)
    version = models.PositiveIntegerField(default=1)
    effective_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    source = models.CharField(max_length=160, default='Jordan liquidity assumptions workbook')
    is_system = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_date', '-version']
        constraints = [models.UniqueConstraint(fields=['entity', 'name'], name='unique_entity_assumption_set_name')]

    def __str__(self):
        return f'{self.entity.slug} · {self.name} v{self.version}'


class LiquidityAssumption(models.Model):
    class Category(models.TextChoices):
        DEPOSIT_RUNOFF = 'deposit_runoff', 'Deposit runoff'
        SECURITY_LIQUIDATION = 'security_liquidation', 'Security liquidation'
        SECURITY_HAIRCUT = 'security_haircut', 'Security haircut'

    assumption_set = models.ForeignKey(LiquidityAssumptionSet, on_delete=models.CASCADE, related_name='rules')
    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=160)
    product_group = models.CharField(max_length=96, blank=True)
    product_type = models.CharField(max_length=96, blank=True)
    currency_scope = models.CharField(max_length=8, default='ALL')
    maturity_breakdown = models.CharField(max_length=32, blank=True)
    value = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'sort_order', 'title']

    def __str__(self):
        return self.title

class PortfolioContract(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name='portfolio_contracts')
    external_id = models.CharField(max_length=64)
    terms = models.JSONField()
    updated = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['external_id']
        constraints = [models.UniqueConstraint(fields=['entity','external_id'], name='unique_entity_contract')]

class CalculationRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        PARTIAL = 'completed_with_exceptions', 'Completed with exceptions'
        INVALID = 'failed_validation', 'Failed validation'
        FAILED = 'failed', 'Failed'
        INTERRUPTED = 'interrupted', 'Interrupted'
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    started = models.DateTimeField(null=True, blank=True)
    finished = models.DateTimeField(null=True, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    entity = models.CharField(max_length=64, help_text='Entity code captured at submission')
    entity_ref = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name='runs')
    as_of_date = models.DateField()
    engine_version = models.CharField(max_length=32)
    input_payload = models.JSONField()
    input_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    result_summary = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ['-created']
        constraints = [
            models.UniqueConstraint(fields=['owner','idempotency_key'], name='unique_user_idempotency_key'),
            models.CheckConstraint(condition=Q(progress__lte=100), name='progress_lte_100'),
        ]

    def __str__(self):
        return f'{self.id} · {self.as_of_date} · {self.status}'

class RunContract(models.Model):
    """Small searchable index of the contracts accepted into a saved run."""
    run = models.ForeignKey(CalculationRun, on_delete=models.CASCADE, related_name='contract_index')
    contract_id = models.CharField(max_length=64)
    contract_id_key = models.CharField(max_length=64)
    product = models.CharField(max_length=32)
    currency = models.CharField(max_length=3)
    direction = models.CharField(max_length=8)

    class Meta:
        ordering = ['contract_id']
        constraints = [models.UniqueConstraint(fields=['run', 'contract_id'], name='unique_run_contract')]
        indexes = [models.Index(fields=['run', 'contract_id_key'], name='run_contract_search_idx')]

class CashFlow(models.Model):
    run = models.ForeignKey(CalculationRun, on_delete=models.CASCADE, related_name='cashflows')
    sequence = models.PositiveIntegerField()
    contract_id = models.CharField(max_length=64)
    product = models.CharField(max_length=32)
    liquidity_product = models.CharField(max_length=96, blank=True)
    liquidity_group = models.CharField(max_length=96, blank=True)
    currency = models.CharField(max_length=3)
    direction = models.CharField(max_length=8)
    payment_date = models.DateField()
    accrual_start = models.DateField()
    accrual_end = models.DateField()
    days_from_asof = models.PositiveIntegerField()
    principal = models.DecimalField(max_digits=24, decimal_places=3)
    interest = models.DecimalField(max_digits=24, decimal_places=3)
    total = models.DecimalField(max_digits=24, decimal_places=3)
    remaining_principal = models.DecimalField(max_digits=24, decimal_places=3)
    bucket = models.CharField(max_length=64)

    class Meta:
        ordering = ['sequence']
        constraints = [models.UniqueConstraint(fields=['run','sequence'], name='unique_run_flow_sequence')]
        indexes = [models.Index(fields=['run','contract_id'], name='flow_run_contract_idx'),
                   models.Index(fields=['run','currency','payment_date'], name='flow_run_currency_date_idx')]
