CREATE TABLE "public"."candidates" (
  "id"           uuid                     NOT NULL DEFAULT gen_random_uuid(),
  "job_id"       uuid                     NOT NULL,
  "name"         text                     NOT NULL,
  "email"        text,
  "linkedin_url" text,
  "cv_text"      text,
  "stage"        text                     NOT NULL DEFAULT 'new'::text,
  "ai_score"     integer,
  "ai_summary"   text,
  "created_at"   timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "candidates_pkey" PRIMARY KEY (id),
  CONSTRAINT "candidates_stage_check" CHECK ((stage = ANY (ARRAY['new'::text, 'screening'::text, 'interview'::text, 'offer'::text, 'hired'::text, 'rejected'::text])))
);

ALTER TABLE "public"."candidates"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."jobs" (
  "id"          uuid                     NOT NULL DEFAULT gen_random_uuid(),
  "customer_id" uuid                     NOT NULL,
  "title"       text                     NOT NULL,
  "description" text,
  "status"      text                     NOT NULL DEFAULT 'open'::text,
  "created_at"  timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "jobs_pkey" PRIMARY KEY (id)
);

ALTER TABLE "public"."jobs"
  ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."jobs"
  ADD CONSTRAINT "jobs_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.profiles(id) ON DELETE CASCADE;

ALTER TABLE "public"."candidates"
  ADD CONSTRAINT "candidates_job_id_fkey" FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."candidates" TO "anon", "authenticated", "postgres", "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."jobs" TO "anon", "authenticated", "postgres", "service_role";
