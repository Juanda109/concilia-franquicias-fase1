"""Domain models for customer data lookup."""

from pydantic import BaseModel, ConfigDict, Field


class CustomerIdentity(BaseModel):
    """Customer identifiers needed to call the external commercial-info API."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(description="Customer identifier received by this API.")
    personal_id: str = Field(description="Personal identifier used by the external API.")
    personal_type: str = Field(description="Personal type used by the external API.")
    customer_name: str = Field(
        default="",
        description="Customer full name used by the external API.",
    )
    first_last_name: str = Field(
        default="",
        description="Customer first last name used by the external API.",
    )
