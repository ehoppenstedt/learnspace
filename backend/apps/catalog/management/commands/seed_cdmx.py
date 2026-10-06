"""Seed realistic CDMX data for development and staging. Never run in production.

    python manage.py seed_cdmx                 # ~200 experiences + test accounts
    python manage.py seed_cdmx --experiences 5000 --reset   # load test for feed latency
"""

import math
import random
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LearnerProfile, ProviderProfile, User
from apps.catalog import services
from apps.catalog.models import (
    Area,
    CancellationPolicy,
    Category,
    Cohort,
    Experience,
    ExperienceMedia,
    ExperienceRevision,
    MediaAsset,
    Session,
    Space,
)
from apps.catalog.seed_content import (
    CONTENT,
    FIRST_NAMES,
    LAST_NAMES,
    MODIFIERS,
    STREETS,
    STUDIO_NAMES,
    STUDIO_PREFIX,
    WHO,
)
from apps.core.geo import public_point

SEED_DOMAIN = "seed.learnspace.local"
TEST_PASSWORD = "learnspace-dev-2026"


class Command(BaseCommand):
    help = "Seed CDMX test data (providers, spaces, experiences, sessions) and test accounts."

    def add_arguments(self, parser):
        parser.add_argument("--experiences", type=int, default=200)
        parser.add_argument("--providers", type=int, default=40)
        parser.add_argument("--reset", action="store_true", help="Delete previous seed data first")
        parser.add_argument("--random-seed", type=int, default=42)

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["reset"] and User.objects.filter(is_staff=False).exclude(email__endswith=SEED_DOMAIN).exists():
            raise CommandError("Refusing to seed a database with real users. Set DEBUG=1 for local/staging.")
        rng = random.Random(opts["random_seed"])
        if opts["reset"]:
            self._reset()
        with transaction.atomic():
            self._accounts()
            providers = self._providers(rng, opts["providers"])
            spaces = self._spaces(rng, providers)
            created = self._experiences(rng, providers, spaces, opts["experiences"])
            space_count = sum(len(v) for v in spaces.values())
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute("ANALYZE")  # fresh planner stats after bulk inserts
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} experiences across {space_count} spaces."))
        self.stdout.write(
            "Test accounts (password for admin; OTP codes print in the server log):\n"
            f"  admin     admin@{SEED_DOMAIN} / {TEST_PASSWORD}  -> http://localhost:8000/admin/\n"
            f"  learner   learner@{SEED_DOMAIN}  phone +52 55 0000 0001\n"
            f"  provider  provider@{SEED_DOMAIN} phone +52 55 0000 0002 (verified)"
        )

    def _reset(self):
        seed_users = User.objects.filter(email__endswith=SEED_DOMAIN)
        experiences = Experience.objects.filter(provider__user__in=seed_users)
        Session.objects.filter(experience__in=experiences).delete()
        Cohort.objects.filter(experience__in=experiences).delete()
        ExperienceRevision.objects.filter(experience__in=experiences).delete()
        ExperienceMedia.objects.filter(experience__in=experiences).delete()
        experiences.delete()
        Space.objects.filter(owner__in=seed_users).delete()
        MediaAsset.objects.filter(owner__in=seed_users).delete()
        ProviderProfile.objects.filter(user__in=seed_users).delete()
        # Users referenced by the append-only audit log are kept (they're seed-only anyway).
        seed_users.filter(is_staff=False).delete()
        self.stdout.write("Previous seed data removed.")

    def _user(self, email, phone, first, last, **extra):
        user, _ = User.objects.get_or_create(email=email, defaults={
            "phone_e164": phone, "phone_verified": True, "email_verified": True, "first_name": first,
            "last_name": last, "date_of_birth": datetime(1990, 1, 15).date(), **extra,
        })
        LearnerProfile.objects.get_or_create(user=user)
        return user

    def _accounts(self):
        admin = self._user(f"admin@{SEED_DOMAIN}", "+525500000000", "Admin", "Learnspace", is_staff=True, is_superuser=True)
        admin.set_password(TEST_PASSWORD)
        admin.save()
        self._user(f"learner@{SEED_DOMAIN}", "+525500000001", "Lucía", "Aprendiz")
        provider = self._user(f"provider@{SEED_DOMAIN}", "+525500000002", "Pablo", "Maestro")
        ProviderProfile.objects.get_or_create(user=provider, defaults={
            "display_name": "Taller de Pablo", "verification_status": "verified",
            "about_me": "Doy clases desde hace 10 años. Me encanta enseñar a principiantes.",
        })

    def _providers(self, rng, count):
        providers = []
        for i in range(count):
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            user = self._user(f"p{i:03d}@{SEED_DOMAIN}", f"+52551{i:07d}", first, last)
            kind = rng.choice(["individual", "individual", "school", "studio"])
            name = f"{first} {last}" if kind == "individual" else f"{rng.choice(STUDIO_PREFIX)} {rng.choice(STUDIO_NAMES)}"
            avatar = self._image(user, f"avatar-{i}", 600, 600)
            profile, _ = ProviderProfile.objects.get_or_create(user=user, defaults={
                "display_name": name, "kind": kind, "verification_status": "verified", "avatar": avatar,
                "about_me": f"Hola, soy {first}. Enseño lo que amo desde hace {rng.randint(3, 20)} años en la CDMX.",
                "about_school": "" if kind == "individual" else f"{name} es un espacio independiente para aprender haciendo.",
                "rating_avg": round(rng.uniform(4.3, 5.0), 2), "rating_count": rng.randint(0, 120),
            })
            providers.append(profile)
        return providers

    def _image(self, owner, slug, w=1200, h=900):
        asset = MediaAsset(owner=owner, kind="image", content_type="image/jpeg", declared_bytes=0, status="ready",
                           external_url=f"https://picsum.photos/seed/{slug}/{w}/{h}", width=w, height=h,
                           dominant_color="#" + "".join(f"{random.Random(slug + str(k)).randint(90, 200):02x}" for k in range(3)))
        asset.storage_key = f"seed/{asset.id}"
        asset.save()
        return asset

    def _spaces(self, rng, providers):
        areas = list(Area.objects.all())
        spaces = {}
        for provider in providers:
            own = []
            for _ in range(rng.choice([1, 1, 2])):
                area = rng.choice(areas)
                # Scatter within ~700 m of the neighborhood centroid.
                dist, bearing = rng.uniform(0, 700), rng.uniform(0, 2 * math.pi)
                lat = area.centroid.y + (dist * math.cos(bearing)) / 111_320
                lng = area.centroid.x + (dist * math.sin(bearing)) / (111_320 * math.cos(math.radians(area.centroid.y)))
                space = Space(owner=provider.user, name=f"{provider.display_name} — {area.name}",
                              about=f"Espacio luminoso en {area.name}, a pasos del transporte público.",
                              address_line=f"{rng.choice(STREETS)} {rng.randint(10, 450)}, {area.name}",
                              neighborhood=area.name, area=area, verification_status="verified")
                space.point_exact = Point(round(lng, 6), round(lat, 6), srid=4326)
                space.point_public = public_point(space.point_exact, salt=str(space.pk))
                space.save()
                own.append(space)
            spaces[provider.pk] = own
        return spaces

    def _experiences(self, rng, providers, spaces, count):
        categories = {c.slug: c for c in Category.objects.all()}
        policy = CancellationPolicy.objects.get(is_default=True)
        now = timezone.now()
        tz = timezone.get_default_timezone()
        today = timezone.localdate()
        created = 0
        all_sessions = []
        for n in range(count):
            slug = rng.choice(list(CONTENT))
            (low, high), items = CONTENT[slug]
            title, learn = rng.choice(items)
            title = (title + rng.choice(MODIFIERS))[:90]
            provider = rng.choice(providers)
            space = rng.choice(spaces[provider.pk])
            offering = rng.choices(["single", "dropin", "course"], weights=[60, 25, 15])[0]
            listed = rng.randrange(low, high + 1, 50) * 100
            if offering == "course":
                listed *= rng.choice([3, 4])
            capacity = rng.choice([4, 6, 8, 10, 12, 15, 20])
            experience = Experience.objects.create(
                provider=provider, status="live", title=title,
                what_you_learn=f"{learn} Al terminar te llevas lo que hiciste y una guía para seguir practicando en casa.",
                who_its_for=rng.choice(WHO), category=categories[slug], instruction_language="en" if "Inglés" in title else "es",
                modality="in_person", offering_type=offering, listed_price_cents=listed, default_capacity=capacity,
                space=space, cancellation_policy=policy, published_at=now,
                rating_avg=round(rng.uniform(4.2, 5.0), 2) if rng.random() < 0.8 else None,
                rating_count=rng.randint(1, 90),
            )
            ExperienceMedia.objects.bulk_create([
                ExperienceMedia(experience=experience, media=self._image(provider.user, f"{slug}-{n}-{k}"), position=k)
                for k in range(rng.randint(3, 6))
            ])
            ExperienceRevision.objects.create(experience=experience, number=1, kind="initial",
                                              payload=services.snapshot(experience), review_status="approved",
                                              submitted_at=now, decided_at=now, reason_code="approved")
            weekend = rng.random() < 0.35
            start_t = time(rng.choice([10, 11, 12])) if weekend else time(rng.choice([18, 19, 20]), rng.choice([0, 30]))
            duration = timedelta(minutes=rng.choice([90, 120, 150, 180]))

            def dt(day, start_t=start_t):
                return timezone.make_aware(datetime.combine(day, start_t), tz)

            first_day = today + timedelta(days=rng.randint(1, 20))
            if weekend:
                first_day += timedelta(days=(5 - first_day.weekday()) % 7)
            if offering == "course":
                cohort = Cohort.objects.create(experience=experience, label="Próximo grupo", capacity=capacity,
                                               seats_booked=rng.randint(0, capacity - 1))
                days = [first_day + timedelta(weeks=w) for w in range(rng.choice([4, 5, 6]))]
                all_sessions += [Session(experience=experience, cohort=cohort, space=space, starts_at=dt(d),
                                         ends_at=dt(d) + duration, capacity=capacity, seats_booked=cohort.seats_booked) for d in days]
            elif offering == "dropin":
                days = [first_day + timedelta(weeks=w) for w in range(6)]
                all_sessions += [Session(experience=experience, space=space, starts_at=dt(d), ends_at=dt(d) + duration,
                                         capacity=capacity, seats_booked=rng.randint(0, capacity)) for d in days]
            else:
                days = sorted({first_day + timedelta(days=rng.randint(0, 35)) for _ in range(rng.randint(1, 4))})
                all_sessions += [Session(experience=experience, space=space, starts_at=dt(d), ends_at=dt(d) + duration,
                                         capacity=capacity, seats_booked=rng.randint(0, capacity)) for d in days]
            created += 1
        for s in all_sessions:
            s.fill_local_fields()
        Session.objects.bulk_create(all_sessions, batch_size=2000)
        for experience in Experience.objects.filter(provider__in=providers, status="live"):
            services.refresh_denorm(experience)
        return created
