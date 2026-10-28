"""图片供应商响应事实；二进制数据只在内存中流转，禁止进入日志和队列。"""

from pydantic import BaseModel, Field, SecretBytes

from module_higgsfield.entity.vo.usage_fact_vo import UsageFact


class ProviderImage(BaseModel):
    ordinal: int
    data: SecretBytes = Field(repr=False, exclude=True)
    revised_prompt: str | None = None


class ImageProviderFact(BaseModel):
    response_id: str | None = None
    images: list[ProviderImage] = Field(default_factory=list)
    usage: dict[str, str] = Field(default_factory=dict)
    usage_fact: UsageFact | None = None
    declared_format: str | None = None
    declared_size: str | None = None
    issues: list[str] = Field(default_factory=list)
    rejected_ordinals: list[int] = Field(default_factory=list)
