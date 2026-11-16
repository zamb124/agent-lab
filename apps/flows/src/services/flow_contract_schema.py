"""JSON Schema контракта flow и Evaluation Lab. Источник — те же Pydantic-модели."""

from __future__ import annotations

from pydantic import BaseModel, TypeAdapter

from apps.flows.src.models.branch_contracts import BranchPayload
from apps.flows.src.models.evaluation_lab.contracts import (
    EvaluationCaseCreateRequest,
    EvaluationCheck,
    EvaluationRubricCreateRequest,
    EvaluationSuiteCreateRequest,
)
from apps.flows.src.models.flow_api import FlowContractSchema, FlowCreateRequest
from apps.flows.src.models.flow_config import Edge
from apps.flows.src.models.node_config import GraphNodeConfig
from apps.flows.src.models.resource import ResourceReference
from apps.flows.src.models.trigger_config import TriggerConfig
from core.types import JsonObject, require_json_object


def _schema(model: type[BaseModel], label: str) -> JsonObject:
    return require_json_object(model.model_json_schema(), label)


def flow_contract_schema() -> FlowContractSchema:
    check_schema = TypeAdapter(EvaluationCheck).json_schema()
    return FlowContractSchema(
        flow_create=_schema(FlowCreateRequest, "FlowCreateRequest"),
        graph_node=_schema(GraphNodeConfig, "GraphNodeConfig"),
        edge=_schema(Edge, "Edge"),
        branch=_schema(BranchPayload, "BranchPayload"),
        trigger=_schema(TriggerConfig, "TriggerConfig"),
        resource_reference=_schema(ResourceReference, "ResourceReference"),
        evaluation_case=_schema(EvaluationCaseCreateRequest, "EvaluationCaseCreateRequest"),
        evaluation_check=require_json_object(check_schema, "EvaluationCheck"),
        evaluation_suite=_schema(EvaluationSuiteCreateRequest, "EvaluationSuiteCreateRequest"),
        evaluation_rubric=_schema(EvaluationRubricCreateRequest, "EvaluationRubricCreateRequest"),
    )
