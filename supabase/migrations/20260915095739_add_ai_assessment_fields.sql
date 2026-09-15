ALTER TABLE "public"."candidates"
  ADD COLUMN "ai_strengths" text[];

ALTER TABLE "public"."candidates"
  ADD COLUMN "ai_gaps" text[];
