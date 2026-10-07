from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Experience
from apps.core.permissions import IsProvider
from apps.reviews import services
from apps.reviews.models import ConductRating, Review

STAR = serializers.IntegerField(min_value=1, max_value=5)


class ReviewInput(serializers.Serializer):
    overall = serializers.IntegerField(min_value=1, max_value=5)
    learning = serializers.IntegerField(min_value=1, max_value=5)
    facilitator = serializers.IntegerField(min_value=1, max_value=5)
    facilities = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    public_text = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    private_feedback = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ConductInput(serializers.Serializer):
    respect = serializers.IntegerField(min_value=1, max_value=5)
    punctuality = serializers.IntegerField(min_value=1, max_value=5)
    admin_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)


def public_review(r: Review) -> dict:
    return {"id": str(r.pk), "author": r.author.first_name, "overall": r.overall, "learning": r.learning,
            "facilitator": r.facilitator, "facilities": r.facilities, "text": r.public_text, "date": r.revealed_at}


class ExperienceReviewsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        experience = get_object_or_404(Experience, pk=pk)
        offset = max(int(request.query_params.get("offset", 0) or 0), 0)
        qs = (Review.objects.filter(experience=experience, revealed_at__isnull=False, moderation="visible")
              .select_related("author").order_by("-revealed_at"))
        page = list(qs[offset: offset + 21])
        return Response({"summary": services.summary(experience), "results": [public_review(r) for r in page[:20]],
                         "next_offset": offset + 20 if len(page) > 20 else None})


class BookingReviewView(APIView):
    """The learner's own review of a booking (always visible to its author)."""

    def get(self, request, pk):
        review = get_object_or_404(Review, booking_id=pk, author=request.user)
        return Response({**public_review(review), "private_feedback": review.private_feedback, "revealed": bool(review.revealed_at)})

    def post(self, request, pk):
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        review = services.submit_review(request.user, pk, data.validated_data)
        return Response({**public_review(review), "revealed": bool(review.revealed_at)}, status=status.HTTP_201_CREATED)


class ConductRatingView(APIView):
    permission_classes = [IsAuthenticated, IsProvider]

    def post(self, request, pk):
        data = ConductInput(data=request.data)
        data.is_valid(raise_exception=True)
        rating = services.submit_conduct_rating(request.user, pk, data.validated_data)
        return Response({"id": str(rating.pk), "revealed": bool(rating.revealed_at)}, status=status.HTTP_201_CREATED)


class PendingView(APIView):
    def get(self, request):
        pending = services.pending_for(request.user)
        return Response({
            "reviews": [{"booking_id": str(b.pk), "experience": b.experience.title, "modality": b.experience.modality,
                         "ended_at": b.ends_at, "closes_at": services.window(b)[1]} for b in pending["reviews"]],
            "conduct_ratings": [{"booking_id": str(b.pk), "experience": b.experience.title, "learner": b.learner.first_name,
                                 "ended_at": b.ends_at, "closes_at": services.window(b)[1]} for b in pending["conduct_ratings"]],
        })


class ProviderReviewsView(APIView):
    """Revealed reviews of my experiences, including the private feedback meant only for me."""

    permission_classes = [IsAuthenticated, IsProvider]

    def get(self, request):
        qs = (Review.objects.filter(experience__provider_id=request.user.pk, revealed_at__isnull=False)
              .select_related("author", "experience").order_by("-revealed_at")[:100])
        return Response([{**public_review(r), "experience": r.experience.title, "private_feedback": r.private_feedback,
                          "hidden": r.moderation == "hidden"} for r in qs])


class MyConductView(APIView):
    def get(self, request):
        from apps.accounts.models import LearnerProfile

        profile = LearnerProfile.objects.filter(user=request.user).first()
        ratings = (ConductRating.objects.filter(learner=request.user, revealed_at__isnull=False)
                   .select_related("booking__experience").prefetch_related("appeals").order_by("-revealed_at"))
        return Response({
            "score": str(profile.conduct_score) if profile and profile.conduct_score is not None else None,
            "count": profile.conduct_count if profile else 0,
            "ratings": [
                {"id": str(r.pk), "experience": r.booking.experience.title, "respect": r.respect, "punctuality": r.punctuality,
                 "date": r.revealed_at, "excluded": r.excluded,
                 "appeal": next(({"status": a.status, "decision_note": a.decision_note} for a in r.appeals.all()), None)}
                for r in ratings
            ],
        })


class AppealView(APIView):
    def post(self, request, pk):
        appeal = services.appeal(request.user, pk, str(request.data.get("statement", "")))
        return Response({"id": str(appeal.pk), "status": appeal.status}, status=status.HTTP_201_CREATED)
