import csv
import json
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiTypes
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .engine import VERSION
from .models import CalculationRun, Entity, EntityConfiguration, PortfolioContract
from .sample import sample
from .serializers import (RunInputSerializer,RunListSerializer,RunDetailSerializer,RunAcceptedSerializer,
                          CashFlowSerializer,FlowPageSerializer,FlowQuerySerializer,RunPageSerializer,HealthSerializer,
                          ContractSearchQuerySerializer,RunContractSerializer,ContractSearchResponseSerializer)
from .services import submit_run


@login_required
@ensure_csrf_cookie
def workspace(request):
    from django.conf import settings
    manifest_path=settings.BASE_DIR/'static'/'app'/'.vite'/'manifest.json'
    if not manifest_path.exists():
        return HttpResponse('Frontend build missing. Run npm ci and npm run build in frontend/.',status=503)
    manifest=json.loads(manifest_path.read_text())
    entry=manifest['index.html']
    return render(request,'cashflows/index.html',{'app_js':'app/'+entry['file'],'app_css':['app/'+f for f in entry.get('css',[])]})

@login_required
def api_guide(request):
    return render(request,'cashflows/api.html')

@extend_schema(responses=HealthSerializer)
@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'status':'ok','version':VERSION,'framework':'Django + Django REST Framework'})

@extend_schema(responses=RunInputSerializer)
@api_view(['GET'])
def sample_input(request):
    return Response(sample())

class NotReady(APIException):
    status_code=409
    default_detail='Run results are not ready.'

class Echo:
    def write(self,value): return value


def csv_response(rows,fields,filename):
    writer=csv.DictWriter(Echo(),fieldnames=fields)
    def stream():
        yield '\ufeff'
        yield writer.writeheader()
        for row in rows: yield writer.writerow(row)
    response=StreamingHttpResponse(stream(),content_type='text/csv; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="{filename}"'
    return response

class RunViewSet(viewsets.GenericViewSet):
    serializer_class=RunDetailSerializer
    lookup_value_regex='[0-9a-fA-F-]{36}'

    def get_queryset(self):
        if getattr(self,'swagger_fake_view',False): return CalculationRun.objects.none()
        qs=CalculationRun.objects.filter(owner=self.request.user).select_related('entity_ref')
        entity=self.request.query_params.get('entity')
        return qs.filter(entity_ref__slug=entity) if entity else qs

    @extend_schema(responses=RunPageSerializer,parameters=[OpenApiParameter('entity',str,description='Filter runs by entity slug.')])
    def list(self,request):
        return Response({'runs':RunListSerializer(self.get_queryset().defer('input_payload','result_summary')[:50],many=True).data})

    @extend_schema(request=RunInputSerializer,responses={202:RunAcceptedSerializer,200:RunAcceptedSerializer,409:OpenApiResponse(description='Idempotency conflict')},
        parameters=[OpenApiParameter('Idempotency-Key',OpenApiTypes.STR,OpenApiParameter.HEADER,description='Optional unique request key, 1–128 characters. Reusing it with identical input returns the same run.')])
    def create(self,request):
        serializer=RunInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key=request.headers.get('Idempotency-Key')
        if key is not None and (not key.strip() or len(key)>128):
            raise ValidationError({'Idempotency-Key':'Use 1–128 nonblank characters.'})
        run,reused=submit_run(request.user,serializer.validated_data,key)
        return Response({'id':str(run.id),'status':run.status,'status_url':f'/api/v1/runs/{run.id}','reused':reused},
                        status=200 if reused else 202)

    @extend_schema(responses=RunDetailSerializer)
    def retrieve(self,request,pk=None):
        return Response(RunDetailSerializer(self.get_object()).data)

    @extend_schema(responses=RunInputSerializer)
    @action(detail=True,methods=['get'],url_path='input')
    def input_snapshot(self,request,pk=None):
        return Response(self.get_object().input_payload)

    def ready_run(self):
        run=self.get_object()
        if run.result_summary is None: raise NotReady()
        return run

    @extend_schema(parameters=[FlowQuerySerializer],responses=FlowPageSerializer)
    @action(detail=True,methods=['get'])
    def cashflows(self,request,pk=None):
        run=self.ready_run()
        filters=FlowQuerySerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        params=filters.validated_data
        queryset=run.cashflows.all()
        for key in ('contract_id','currency','product'):
            if key in params: queryset=queryset.filter(**{key:params[key]})
        total=queryset.count()
        offset,limit=params['offset'],params['limit']
        return Response({'total':total,'offset':offset,'limit':limit,'cashflows':CashFlowSerializer(queryset[offset:offset+limit],many=True).data})

    @extend_schema(parameters=[ContractSearchQuerySerializer],responses=ContractSearchResponseSerializer)
    @action(detail=True,methods=['get'])
    def contracts(self,request,pk=None):
        """Prefix search only: avoids loading a whole bank portfolio into a browser."""
        run=self.ready_run()
        filters=ContractSearchQuerySerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        query=filters.validated_data['q'].strip()
        limit=filters.validated_data['limit']
        indexed=run.contract_index.filter(contract_id_key__startswith=query.upper())[:limit]
        if indexed:
            return Response({'query':query,'contracts':RunContractSerializer(indexed,many=True).data})
        # Runs created before the contract index was introduced are small legacy
        # prototypes. New bank-scale runs always use the indexed path above.
        legacy=(run.result_summary or {}).get('contracts',[])
        matches=[item for item in legacy if item.get('contract_id','').upper().startswith(query.upper())][:limit]
        return Response({'query':query,'contracts':matches})

    @extend_schema(responses={(200,'text/csv'):OpenApiTypes.BINARY})
    @action(detail=True,methods=['get'],url_path=r'cashflows\.csv')
    def cashflows_csv(self,request,pk=None):
        run=self.ready_run()
        fields=list(CashFlowSerializer().fields)
        rows=(CashFlowSerializer(flow).data for flow in run.cashflows.iterator(chunk_size=1000))
        return csv_response(rows,fields,f'{run.id}-cashflows.csv')

    @extend_schema(responses={(200,'text/csv'):OpenApiTypes.BINARY})
    @action(detail=True,methods=['get'],url_path=r'summary\.csv')
    def summary_csv(self,request,pk=None):
        run=self.ready_run()
        fields=['currency','bucket','inflow_principal','inflow_interest','outflow_principal','outflow_interest','inflows','outflows','net_gap','cumulative_gap']
        rows=(dict(currency=cur,**row) for cur,rows in run.result_summary['summary'].items() for row in rows)
        return csv_response(rows,fields,f'{run.id}-summary.csv')

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True,methods=['get'],url_path=r'result\.json')
    def result_json(self,request,pk=None):
        run=self.ready_run()
        # Small-scale prototype export; use streaming columnar output for full bank workloads.
        data=dict(run.result_summary,cashflows=CashFlowSerializer(run.cashflows.all(),many=True).data)
        response=Response(data)
        response['Content-Disposition']=f'attachment; filename="{run.id}.json"'
        return response
