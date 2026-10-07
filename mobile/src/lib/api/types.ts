export type Money = { listed_cents: number; fee_cents: number; total_cents: number; currency: 'MXN' };

export type Category = { id: number; slug: string; name: string; icon: string };

export type Media = {
  id: string;
  kind: 'image' | 'video';
  width: number | null;
  height: number | null;
  color: string;
  urls?: { w400: string; w800: string; w1600: string };
  video_url?: string;
  poster_url?: string | null;
  duration_s?: number;
  status?: string;
};

export type Modality = 'in_person' | 'online';
export type OfferingType = 'single' | 'course' | 'dropin';

export type ExperienceCard = {
  id: string;
  title: string;
  category: Category | null;
  media: Media[];
  price: Money;
  distance_m: number | null;
  next_session_at: string | null;
  seats_left: number | null;
  rating_avg: string | null;
  rating_count: number;
  area: string | null;
  modality: Modality;
  offering_type: OfferingType;
  instruction_language: string;
  provider_name: string;
};

export type PolicyRule = {
  applies_to: 'learner_cancel' | 'no_show';
  min_hours_before: number;
  max_hours_before: number | null;
  listed_refund_pct: number;
  refund_fee: boolean;
};

export type Policy = { id: number; code: string; name: string; description: string; rules: PolicyRule[] };

export type ProviderPublic = {
  id: string;
  display_name: string;
  kind: string;
  about_me: string;
  about_school: string;
  is_verified: boolean;
  rating_avg: string | null;
  rating_count: number;
  avatar: Media | null;
  member_since: string;
};

export type SessionPublic = { id: string; starts_at: string; ends_at: string; seats_left: number; cohort_id: string | null };
export type CohortPublic = { id: string; label: string; seats_left: number; sessions: { starts_at: string; ends_at: string }[] };

export type Location =
  | { approximate: true; lat: number; lng: number; radius_m: number }
  | { approximate: false; lat: number; lng: number; address_line: string; address_reference: string | null };

export type ExperienceDetail = ExperienceCard & {
  what_you_learn: string;
  who_its_for: string;
  provider: ProviderPublic;
  space: {
    id: string;
    name: string;
    about: string;
    neighborhood: string;
    area: string;
    media: Media[];
  } | null;
  location: Location | null;
  cancellation_policy: Policy | null;
  upcoming: { sessions?: SessionPublic[]; cohorts?: CohortPublic[] };
};

export type FeedPage = { results: ExperienceCard[]; next_offset: number | null };

export type MapPin = { id: string; title: string; lat: number; lng: number; total_cents: number; icon: string };

export type Area = { slug: string; name: string; borough: string; city: string; centroid: { lat: number; lng: number } };

export type AppConfig = {
  brand: string;
  currency: 'MXN';
  fee_bps: number;
  languages: string[];
  categories: Category[];
  cancellation_policies: Policy[];
  features: { online_experiences: boolean; payments_test_mode: boolean };
  feed: { default_radius_km: number; max_radius_km: number };
  media: { max_images: number; max_videos: number; max_image_bytes: number; max_video_bytes: number; max_video_seconds: number };
  legal: { entity: string; rfc: string; privacy_notice_version: string };
};

export type Me = {
  id: string;
  email: string | null;
  email_verified: boolean;
  phone_e164: string | null;
  phone_verified: boolean;
  first_name: string;
  last_name: string;
  date_of_birth: string | null;
  ui_language: 'es' | 'en';
  profile_complete: boolean;
  is_provider: boolean;
  provider: { display_name: string; kind: string; verification_status: string } | null;
  bio: string;
  fluent_languages: string[];
  has_accessibility_needs: boolean;
  conduct_score: string | null;
};

export type Session = { access: string; refresh: string; created: boolean; user: Me };

export type ExperienceStatus = 'draft' | 'in_review' | 'changes_requested' | 'live' | 'paused' | 'expired' | 'rejected';

export type ProviderExperience = {
  id: string;
  status: ExperienceStatus;
  title: string;
  what_you_learn: string;
  who_its_for: string;
  category: Category | null;
  category_id: number | null;
  instruction_language: string;
  modality: Modality;
  offering_type: OfferingType;
  listed_price_cents: number;
  price: Money;
  default_capacity: number;
  space_id: string | null;
  online_url: string | null;
  cancellation_policy_id: number | null;
  publish_until: string | null;
  requires_approval_below: string | null;
  media: Media[];
  media_ids: string[];
  next_session_at: string | null;
  pending_changes: { revision: number; review_status: 'draft' | 'pending'; changed_fields: string[] } | null;
  last_decision: { review_status: string; reason_code: string; reviewer_note: string; decided_at: string } | null;
  sessions_upcoming: number;
};

export type ProviderSession = {
  id: string;
  cohort_id: string | null;
  starts_at: string;
  ends_at: string;
  capacity: number;
  seats_booked: number;
  seats_left: number;
  status: string;
};

export type ProviderSpace = {
  id: string;
  name: string;
  about: string;
  address_line: string;
  address_reference: string | null;
  neighborhood: string;
  city: string;
  location: { exact: { lat: number; lng: number }; public: { lat: number; lng: number }; area: string | null };
  verification_status: string;
  media: Media[];
};

export type ProviderProfile = {
  display_name: string;
  about_me: string;
  about_school: string;
  kind: 'individual' | 'school' | 'studio';
  avatar: string | null;
  verification_status: 'unverified' | 'pending' | 'verified' | 'rejected';
  rating_avg: string | null;
  rating_count: number;
};

export type ApiErrorBody = { error: { code: string; message: string; fields: Record<string, unknown>; retry_after?: number } };

// ------------------------------------------------------------------ Phase 2

export type BookingStatus =
  | 'pending_payment' | 'pending_approval' | 'confirmed' | 'declined' | 'payment_failed' | 'cancelled' | 'completed' | 'no_show';

export type Hold = { hold_id: string; expires_at: string; seats: number; price: Money };

export type PaymentSheetParams = {
  payment_intent_client_secret: string;
  customer_id: string;
  customer_ephemeral_key: string | null;
  publishable_key: string;
  gateway: 'stripe' | 'fake';
};

export type Booking = {
  id: string;
  code: string;
  status: BookingStatus;
  seats: number;
  starts_at: string;
  ends_at: string;
  experience: { id: string; title: string; cover: Media | null; category: string | null; offering_type: OfferingType };
  sessions: { id: string; starts_at: string; ends_at: string; status: string; attendance: string }[];
  price: { listed_cents: number; fee_cents: number; total_cents: number; fee_bps: number; currency: 'MXN' };
  location:
    | { approximate: false; lat: number; lng: number; address_line: string; address_reference: string | null; neighborhood: string; space_name: string }
    | { approximate: true; lat: number; lng: number; neighborhood: string }
    | null;
  provider: { id: string; display_name: string };
  policy: { code: string; name_es: string; name_en: string; rules: PolicyRule[] };
  refunded_cents: number;
  can_cancel: boolean;
  approval_deadline: string | null;
  review_pending: boolean;
  calendar_url?: string;
};

export type CancellationQuote = {
  booking_id: string;
  listed_refund_cents: number;
  fee_refund_cents: number;
  refund_cents: number;
  hours_before_start: string;
  not_charged: boolean;
  quote_token: string;
  valid_for_seconds: number;
};

export type RosterAttendee = {
  booking_id: string;
  code: string;
  status: BookingStatus;
  seats: number;
  attendance: 'unknown' | 'present' | 'absent';
  learner: {
    first_name: string;
    last_initial: string;
    conduct_score: string | null;
    conduct_count: number;
    fluent_languages: string[];
    accessibility_needs: string | null;
  };
};

export type ProviderBooking = {
  id: string;
  code: string;
  status: BookingStatus;
  seats: number;
  starts_at: string;
  experience_title: string;
  listed_cents: number;
  approval_deadline: string | null;
  learner: { first_name: string; conduct_score: string | null; conduct_count: number };
};

export type OnboardingStatus = {
  ready_to_publish: boolean;
  missing: ('identity' | 'payment_account' | 'tax_profile')[];
  identity_status: string;
  payment_account: { kyc_status: string; payouts_enabled: boolean; requirements_due: string[] } | null;
  tax_profile: { person_type: 'fisica' | 'moral'; rfc: string; legal_name: string; validated: boolean } | null;
};

export type Earnings = {
  withholding_configured: boolean;
  test_mode: boolean;
  totals: { upcoming_cents: number; on_hold_cents: number; paid_cents: number };
  transfers: {
    id: string; booking_code: string; experience: string; gross_cents: number; isr_withheld_cents: number;
    iva_withheld_cents: number; net_cents: number; status: string; release_at: string; sent_at: string | null; hold_reason: string;
  }[];
};

export type SavedCard = { id: string; brand: string; last4: string; exp_month: number; exp_year: number };
export type NotificationPrefs = { push: boolean; email: boolean; reminders: boolean };
