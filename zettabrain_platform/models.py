from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class SystemRole(str, Enum):
    admin = "admin"
    user  = "user"


class TeamRole(str, Enum):
    manager = "manager"
    member  = "member"
    viewer  = "viewer"


class ModelRequestStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# -------------------------------------------------------
# System Config (key-value store for admin settings)
# -------------------------------------------------------
class SystemConfig(SQLModel, table=True):
    key:   str = Field(primary_key=True)
    value: str = ""


# -------------------------------------------------------
# Users
# -------------------------------------------------------
class User(SQLModel, table=True):
    id:                   Optional[int] = Field(default=None, primary_key=True)
    username:             str           = Field(unique=True, index=True)
    email:                str           = Field(unique=True)
    hashed_pw:            str
    system_role:          SystemRole    = Field(default=SystemRole.user)
    is_active:            bool          = Field(default=True)
    must_change_password: bool          = Field(default=False)
    created_at:           datetime      = Field(default_factory=datetime.utcnow)

    memberships: List["TeamMember"] = Relationship(back_populates="user")
    audit_logs:  List["AuditLog"]   = Relationship(back_populates="user")


# -------------------------------------------------------
# Teams
# -------------------------------------------------------
class Team(SQLModel, table=True):
    id:           Optional[int] = Field(default=None, primary_key=True)
    name:         str           = Field(unique=True)
    slug:         str           = Field(unique=True, index=True)
    description:  Optional[str] = None
    docs_folder:  Optional[str] = None
    created_at:   datetime      = Field(default_factory=datetime.utcnow)

    # Team-specific model configuration (NULL = use system defaults)
    llm_provider:   Optional[str] = None
    llm_model:      Optional[str] = None
    embed_provider: Optional[str] = None
    embed_model:    Optional[str] = None

    # Generation features
    skills_enabled: bool = Field(default=True)

    members:        List["TeamMember"]    = Relationship(back_populates="team")
    audit_logs:     List["AuditLog"]      = Relationship(back_populates="team")
    model_requests: List["ModelRequest"]  = Relationship(back_populates="team")


# -------------------------------------------------------
# Team membership (join table with role)
# -------------------------------------------------------
class TeamMember(SQLModel, table=True):
    id:        Optional[int] = Field(default=None, primary_key=True)
    user_id:   int           = Field(foreign_key="user.id")
    team_id:   int           = Field(foreign_key="team.id")
    team_role: TeamRole      = Field(default=TeamRole.member)
    joined_at: datetime      = Field(default_factory=datetime.utcnow)

    user: Optional["User"] = Relationship(back_populates="memberships")
    team: Optional["Team"] = Relationship(back_populates="members")


# -------------------------------------------------------
# Model Requests
# -------------------------------------------------------
class ModelRequest(SQLModel, table=True):
    id:              Optional[int]         = Field(default=None, primary_key=True)
    team_id:         int                   = Field(foreign_key="team.id")
    requester_id:    int                   = Field(foreign_key="user.id")

    llm_provider:    Optional[str]         = None
    llm_model:       Optional[str]         = None
    embed_provider:  Optional[str]         = None
    embed_model:     Optional[str]         = None

    justification:   str
    status:          ModelRequestStatus    = Field(default=ModelRequestStatus.pending)

    reviewed_by:     Optional[int]         = Field(default=None, foreign_key="user.id")
    reviewed_at:     Optional[datetime]    = None
    rejection_reason: Optional[str]        = None

    created_at:      datetime              = Field(default_factory=datetime.utcnow)

    team:     Optional["Team"] = Relationship(back_populates="model_requests")
    requester: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ModelRequest.requester_id]"}
    )
    reviewer:  Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ModelRequest.reviewed_by]"}
    )


# -------------------------------------------------------
# Audit log (covers both chat and generation actions)
# -------------------------------------------------------
class AuditLog(SQLModel, table=True):
    id:               Optional[int]   = Field(default=None, primary_key=True)
    user_id:          Optional[int]   = Field(default=None, foreign_key="user.id")
    team_id:          Optional[int]   = Field(default=None, foreign_key="team.id")
    action:           str             # "chat" | "generate" | "ingest" | "refine"
    query:            Optional[str]   = None
    response_preview: Optional[str]   = None
    chunks_used:      Optional[int]   = None
    model:            Optional[str]   = None
    confidence:       Optional[float] = None
    duration_ms:      Optional[int]   = None
    timestamp:        datetime        = Field(default_factory=datetime.utcnow)
    # Provenance
    query_hash:       Optional[str]   = None
    chunk_hashes:     Optional[str]   = None
    answer_hash:      Optional[str]   = None
    provenance_sig:   Optional[str]   = None
    # Generation-specific
    skill_name:       Optional[str]   = None
    document_id:      Optional[str]   = None

    user: Optional["User"] = Relationship(back_populates="audit_logs")
    team: Optional["Team"] = Relationship(back_populates="audit_logs")


# -------------------------------------------------------
# Generated Documents (from skills engine)
# -------------------------------------------------------
class GeneratedDocument(SQLModel, table=True):
    id:                str             = Field(primary_key=True)
    team_id:           int             = Field(foreign_key="team.id")
    user_id:           int             = Field(foreign_key="user.id")
    skill_name:        str
    skill_display:     str
    customer_name:     Optional[str]   = None
    customer_email:    Optional[str]   = None
    customer_phone:    Optional[str]   = None
    request:           str
    content:           str
    citations:         Optional[str]   = None  # JSON array
    generation_time_ms: Optional[int]  = None
    created_at:        datetime        = Field(default_factory=datetime.utcnow)


# -------------------------------------------------------
# Pydantic schemas
# -------------------------------------------------------
class UserCreate(SQLModel):
    username: str
    email:    str
    password: str


class UserRead(SQLModel):
    id:          int
    username:    str
    email:       str
    system_role: SystemRole
    is_active:   bool
    created_at:  datetime


class TeamCreate(SQLModel):
    name:        str
    description: Optional[str] = None
    docs_folder: Optional[str] = None


class TeamRead(SQLModel):
    id:          int
    name:        str
    slug:        str
    description: Optional[str]
    docs_folder: Optional[str]
    created_at:  datetime


class TeamUpdate(SQLModel):
    name:        Optional[str] = None
    description: Optional[str] = None
    docs_folder: Optional[str] = None


class TeamMemberRead(SQLModel):
    user_id:   int
    username:  str
    email:     str
    team_role: TeamRole
    joined_at: datetime


class ChatRequest(SQLModel):
    question: str
    team_id:  int


class ChatResponse(SQLModel):
    answer:      str
    confidence:  float
    chunks:      int
    duration_ms: int
    sources:     List[str]


class GenerateRequest(SQLModel):
    skill_file:     str
    input_text:     str
    team_id:        int
    customer_name:  str = ""
    customer_email: str = ""
    customer_phone: str = ""


class GenerateResponse(SQLModel):
    id:                str
    skill_name:        str
    content:           str
    citations:         List[str]
    generation_time_ms: int


class Token(SQLModel):
    access_token:         str
    token_type:           str  = "bearer"
    must_change_password: bool = False


class ChangePasswordRequest(SQLModel):
    new_password: str
