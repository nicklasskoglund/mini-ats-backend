ALTER TABLE "public"."candidates"
  ADD COLUMN "phone" text;

ALTER TABLE "public"."candidates"
  ADD COLUMN "notes" text;

ALTER TABLE "public"."profiles"
  ADD COLUMN "website_url" text;

ALTER TABLE "public"."profiles"
  ADD COLUMN "linkedin_url" text;

ALTER TABLE "public"."profiles"
  ADD COLUMN "phone" text;

ALTER TABLE "public"."profiles"
  ADD COLUMN "contact_email" text;

ALTER TABLE "public"."profiles"
  ADD COLUMN "address" text;

ALTER TABLE "public"."profiles"
  ADD COLUMN "description" text;
