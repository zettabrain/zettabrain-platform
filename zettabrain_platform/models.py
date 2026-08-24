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

    # Skills/generation toggle
    skills_enabled: bool = Field(default=True)

    # Multi-embedding storage
    multi_embed_allowed: bool = Field(default=False)
    multi_embed_enabled: bool = Field(default=False)

    # Team-specific model configuration (NULL = use system defaults)
    llm_provider:   Optional[str] = None
    llm_model:      Optional[str] = None
    embed_provider: Optional[str] = None
    embed_model:    Optional[str] = None

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
# Model Requests (team-level model configuration requests)
# -------------------------------------------------------
class ModelRequest(SQLModel, table=True):
    id:              Optional[int]         = Field(default=None, primary_key=True)
    team_id:         int                   = Field(foreign_key="team.id")
    requester_id:    int                   = Field(foreign_key="user.id")

    # Requested model configuration
    llm_provider:    Optional[str]         = None
    llm_model:       Optional[str]         = None
    embed_provider:  Optional[str]         = None
    embed_model:     Optional[str]         = None

    justification:   str                   # Why this model is needed
    status:          ModelRequestStatus    = Field(default=ModelRequestStatus.pending)

    # Admin review
    reviewed_by:     Optional[int]         = Field(default=None, foreign_key="user.id")
    reviewed_at:     Optional[datetime]    = None
    rejection_reason: Optional[str]        = None

    created_at:      datetime              = Field(default_factory=datetime.utcnow)

    # Relationships
    team:     Optional["Team"] = Relationship(back_populates="model_requests")
    requester: Optional["User"] = Relationship(sa_relationship_kwargs={"foreign_keys": "[ModelRequest.requester_id]"})
    reviewer:  Optional["User"] = Relationship(sa_relationship_kwargs={"foreign_keys": "[ModelRequest.reviewed_by]"})


# -------------------------------------------------------
# Audit log
# -------------------------------------------------------
class AuditLog(SQLModel, table=True):
    id:               Optional[int]   = Field(default=None, primary_key=True)
    user_id:          Optional[int]   = Field(default=None, foreign_key="user.id")
    team_id:          Optional[int]   = Field(default=None, foreign_key="team.id")
    action:           str
    query:            Optional[str]   = None
    response_preview: Optional[str]   = None
    chunks_used:      Optional[int]   = None
    model:            Optional[str]   = None
    confidence:       Optional[float] = None
    duration_ms:      Optional[int]   = None
    timestamp:        datetime        = Field(default_factory=datetime.utcnow)
    # ZettaBrain Verified — cryptographic answer provenance
    query_hash:       Optional[str]   = None  # SHA-256 of the query
    chunk_hashes:     Optional[str]   = None  # JSON array of SHA-256 hashes per chunk
    answer_hash:      Optional[str]   = None  # SHA-256 of the answer
    provenance_sig:   Optional[str]   = None  # Ed25519 hex signature over the bundle

    user: Optional["User"] = Relationship(back_populates="audit_logs")
    team: Optional["Team"] = Relationship(back_populates="audit_logs")


# -------------------------------------------------------
# Pydantic schemas (not table=True)
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
    multi_embed_allowed: bool = False
    multi_embed_enabled: bool = False


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


class Token(SQLModel):
    access_token:         str
    token_type:           str  = "bearer"
    must_change_password: bool = False


class ChangePasswordRequest(SQLModel):
    new_password: str


class ModelRequestCreate(SQLModel):
    llm_provider:   Optional[str] = None
    llm_model:      Optional[str] = None
    embed_provider: Optional[str] = None
    embed_model:    Optional[str] = None
    justification:  str           = Field(min_length=20)


class ModelRequestRead(SQLModel):
    id:               int
    team_id:          int
    team_name:        str
    requester_id:     int
    requester_username: str
    llm_provider:     Optional[str]
    llm_model:        Optional[str]
    embed_provider:   Optional[str]
    embed_model:      Optional[str]
    justification:    str
    status:           ModelRequestStatus
    reviewed_by:      Optional[int]
    reviewer_username: Optional[str] = None  # Added: username of reviewer
    reviewed_at:      Optional[datetime]
    rejection_reason: Optional[str]
    created_at:       datetime


class ModelRequestReject(SQLModel):
    reason: str = Field(min_length=10)


class TeamModelConfig(SQLModel):
    llm_provider:   Optional[str] = None
    llm_model:      Optional[str] = None
    embed_provider: Optional[str] = None
    embed_model:    Optional[str] = None


class TeamModelConfigRead(SQLModel):
    team_id:        int
    team_name:      str
    llm_provider:   str
    llm_model:      str
    embed_provider: str
    embed_model:    str
    llm_from_team:  bool
    embed_from_team: bool
