create table if not exists flows (
  id varchar(64) primary key,
  name varchar(255) not null,
  description text,
  owner_user_id varchar(64),
  workspace_id varchar(64),
  status varchar(32) not null default 'draft',
  latest_version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists flow_versions (
  id varchar(64) primary key,
  flow_id varchar(64) not null references flows(id),
  version integer not null,
  status varchar(32) not null default 'draft',
  version_note varchar(255),
  input_schema_json jsonb not null default '{}'::jsonb,
  output_schema_json jsonb not null default '{}'::jsonb,
  definition_json jsonb not null,
  created_at timestamptz not null default now(),
  unique (flow_id, version)
);

create table if not exists agents (
  id varchar(64) primary key,
  name varchar(255) not null,
  slug varchar(128) unique,
  description text,
  source_type varchar(32) not null default 'user_defined',
  owner_user_id varchar(64),
  workspace_id varchar(64),
  role varchar(128),
  system_prompt text,
  instructions text,
  model_provider varchar(64) not null,
  model_name varchar(128) not null,
  model_config_json jsonb not null default '{}'::jsonb,
  input_schema_json jsonb not null default '{}'::jsonb,
  output_schema_json jsonb not null default '{}'::jsonb,
  tool_ids_json jsonb not null default '[]'::jsonb,
  knowledge_ids_json jsonb not null default '[]'::jsonb,
  timeout_seconds integer not null default 120,
  retry_policy_json jsonb not null default '{"max_retries": 1, "retry_backoff_seconds": 3}'::jsonb,
  version integer not null default 1,
  status varchar(32) not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists skills (
  id varchar(64) primary key,
  name varchar(255) not null,
  description text,
  kind varchar(64) not null,
  config_json jsonb not null default '{}'::jsonb,
  status varchar(32) not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists resources (
  id varchar(64) primary key,
  name varchar(255) not null,
  type varchar(64) not null,
  description text,
  config_json jsonb not null default '{}'::jsonb,
  status varchar(32) not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists agent_skills (
  id varchar(64) primary key,
  agent_id varchar(64) not null references agents(id),
  skill_id varchar(64) not null references skills(id),
  sort_order integer not null default 0,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (agent_id, skill_id)
);

create table if not exists agent_resources (
  id varchar(64) primary key,
  agent_id varchar(64) not null references agents(id),
  resource_id varchar(64) not null references resources(id),
  binding_config_json jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (agent_id, resource_id)
);

create table if not exists runs (
  id varchar(64) primary key,
  flow_id varchar(64) not null references flows(id),
  flow_version_id varchar(64) not null references flow_versions(id),
  status varchar(32) not null default 'queued',
  trigger_type varchar(32) not null default 'manual',
  user_id varchar(64),
  session_id varchar(64),
  input_json jsonb not null default '{}'::jsonb,
  runtime_context_json jsonb not null default '{}'::jsonb,
  output_json jsonb not null default '{}'::jsonb,
  error_message text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists run_steps (
  id varchar(64) primary key,
  run_id varchar(64) not null references runs(id),
  node_id varchar(64) not null,
  node_key varchar(128),
  node_type varchar(32) not null,
  agent_id varchar(64),
  step_index integer not null,
  attempt integer not null default 1,
  status varchar(32) not null default 'pending',
  input_json jsonb not null default '{}'::jsonb,
  output_json jsonb not null default '{}'::jsonb,
  resolved_config_json jsonb not null default '{}'::jsonb,
  error_message text,
  usage_json jsonb not null default '{}'::jsonb,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists run_events (
  id bigserial primary key,
  run_id varchar(64) not null references runs(id),
  run_step_id varchar(64),
  event_type varchar(64) not null,
  event_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists knowledge_documents (
  id varchar(64) primary key,
  resource_id varchar(64) not null references resources(id),
  title varchar(255) not null,
  source_type varchar(32) not null,
  source_uri text,
  status varchar(32) not null default 'pending',
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_flows_status on flows(status);
create index if not exists idx_flows_owner_updated_at on flows(owner_user_id, updated_at desc);
create index if not exists idx_flow_versions_flow_version on flow_versions(flow_id, version desc);
create index if not exists idx_agents_owner_updated_at on agents(owner_user_id, updated_at desc);
create index if not exists idx_agents_workspace_updated_at on agents(workspace_id, updated_at desc);
create index if not exists idx_resources_type_status on resources(type, status);
create index if not exists idx_runs_flow_created_at on runs(flow_id, created_at desc);
create index if not exists idx_runs_status_created_at on runs(status, created_at desc);
create index if not exists idx_run_steps_run_step_index on run_steps(run_id, step_index);
create index if not exists idx_run_events_run_created_at on run_events(run_id, created_at);
create index if not exists idx_knowledge_documents_resource_status on knowledge_documents(resource_id, status);
