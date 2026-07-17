from pydantic import BaseModel, Field
from typing import Any, Literal
class Column(BaseModel):
    name: str; data_type: str="string"; editable: bool=True
class RequirementTable(BaseModel):
    title: str="Requirements Specification"; columns:list[Column]; rows:list[list[Any]]
class Version(BaseModel):
    version:str; timestamp:str; source:str; table:RequirementTable; analysis:str=""; stakeholder_needs:str=""
class Session(BaseModel):
    id:str; title:str="Untitled session"; stakeholder_needs:str=""; analysis:str=""; clarification_questions:list[str]=Field(default_factory=list); files:list[str]=Field(default_factory=list); versions:list[Version]=Field(default_factory=list); active_version:int=-1; messages:list[dict[str,str]]=Field(default_factory=list)
class AnalyzeRequest(BaseModel):
    stakeholder_needs:str; additional_context:str=""; clarification_answers:str=""; direct_generation:bool=False; template_columns:list[str]|None=None
class GenerateRequest(BaseModel): template_columns:list[str]|None=None
class TableRequest(BaseModel): columns:list[Column]; rows:list[list[Any]]; source:str="user_edit"
class ActionRequest(BaseModel): text:str
class LlmConfigRequest(BaseModel):
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
class ApiResult(BaseModel): success:bool=True; stage:str="complete"; data:dict[str,Any]=Field(default_factory=dict); error:str|None=None
