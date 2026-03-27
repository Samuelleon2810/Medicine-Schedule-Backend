-- Ejecutar en Supabase SQL Editor para habilitar estadísticas de ventas.
-- La tabla se rellena automáticamente al usar POST /medicamentos/vender.

create table if not exists public.ventas (
  id bigserial primary key,
  medicamento_id bigint not null,
  cantidad integer not null,
  monto_total numeric(10,2) not null,
  created_at timestamptz default now()
);

-- Opcional: permitir acceso sin RLS para desarrollo (igual que inventario)
alter table public.ventas disable row level security;
grant usage on schema public to public;
grant insert, select on table public.ventas to public;
