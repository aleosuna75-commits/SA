-- Nuestro Nido: base de datos compartida. Pégalo completo en Supabase → SQL Editor → Run.
create table if not exists public.docs (
  col        text        not null,
  id         text        not null,
  data       jsonb       not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (col, id)
);

-- Solo quien inició sesión puede leer y escribir. Los únicos usuarios son los dos que crearás a mano
-- (con los registros nuevos apagados), así que nadie más entra.
alter table public.docs enable row level security;
drop policy if exists "solo con sesion" on public.docs;
drop policy if exists "abierto" on public.docs; -- por si antes se usó el modo abierto
create policy "solo con sesion" on public.docs for all to authenticated using (true) with check (true);

-- Permisos sobre la tabla: los proyectos nuevos de Supabase ya no los dan solos.
revoke all on public.docs from anon;
grant select, insert, update, delete on public.docs to authenticated;

-- Para que lo que captura uno le aparezca al otro al instante. Todo el archivo se puede ejecutar más de una vez.
do $$ begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'docs') then
    alter publication supabase_realtime add table public.docs;
  end if;
end $$;
