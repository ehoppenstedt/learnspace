import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Circle, MapView, Marker } from '@/components/map';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { PhotoCarousel } from '@/components/PhotoCarousel';
import { ReportSheet } from '@/components/ReportSheet';
import { RatingBar, Stars } from '@/components/Stars';
import { Button, ErrorState, Section } from '@/components/ui';
import { useExperience, useExperienceReviews } from '@/lib/api/hooks';
import { openThreadForBooking } from '@/lib/messaging';
import type { ExperienceDetail } from '@/lib/api/types';
import { useAuth } from '@/lib/auth/AuthContext';
import { formatMoney, formatSessionDate, formatTimeRange } from '@/lib/utils/format';
import { colors, radius, shadow, space, type } from '@/theme/tokens';

export default function ExperienceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useTranslation();
  const query = useExperience(id);
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();

  if (query.isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }
  if (query.isError || !query.data) {
    return (
      <SafeAreaView style={{ flex: 1 }}>
        <ErrorState message={t('errors.generic')} onRetry={() => query.refetch()} />
      </SafeAreaView>
    );
  }
  const e = query.data;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView contentContainerStyle={{ paddingBottom: 120 }}>
        <PhotoCarousel media={e.media} width={width} height={Math.round(width * 0.82)} size="w1600" />
        <View style={styles.body}>
          <Header e={e} />
          <HostRow e={e} />
          <Section title={t('detail.whatYouLearn')}>
            <Text style={type.body}>{e.what_you_learn}</Text>
          </Section>
          <Section title={t('detail.whoFor')}>
            <Text style={type.body}>{e.who_its_for}</Text>
          </Section>
          <Upcoming e={e} />
          {e.location ? <Where e={e} /> : null}
          {e.space?.about ? (
            <Section title={t('detail.aboutSpace')}>
              <Text style={type.body}>{e.space.about}</Text>
              <SpacePhotos e={e} />
            </Section>
          ) : null}
          <AboutHost e={e} />
          <Reviews e={e} />
          {e.cancellation_policy ? (
            <Section title={t('detail.policy')} last>
              <Text style={type.bodyStrong}>{e.cancellation_policy.name}</Text>
              <Text style={[type.small, { marginTop: space.sm }]}>{e.cancellation_policy.description}</Text>
            </Section>
          ) : null}
          <ReportLink id={e.id} />
        </View>
      </ScrollView>

      <Pressable
        onPress={() => router.back()}
        style={[styles.back, shadow.card, { top: insets.top + 8 }]}
        accessibilityLabel={t('common.back')}
      >
        <Ionicons name="chevron-back" size={22} color={colors.text} />
      </Pressable>

      <BookingBar e={e} bottom={insets.bottom} />
    </View>
  );
}

function Header({ e }: { e: ExperienceDetail }) {
  const { t, i18n } = useTranslation();
  return (
    <View style={{ paddingTop: space.xl, paddingBottom: space.lg }}>
      <Text style={type.display}>{e.title}</Text>
      <Text style={[type.small, { marginTop: space.sm }]}>
        {[e.category?.name, e.area, e.instruction_language === 'en' ? 'English' : 'Español'].filter(Boolean).join(' · ')}
      </Text>
      {e.next_session_at ? (
        <Text style={[type.small, { marginTop: 2 }]}>
          {formatSessionDate(e.next_session_at, i18n.language)}
          {e.seats_left !== null && e.seats_left <= 5 ? ` · ${t('feed.seatsLeft', { count: e.seats_left })}` : ''}
        </Text>
      ) : null}
    </View>
  );
}

function HostRow({ e }: { e: ExperienceDetail }) {
  const { t } = useTranslation();
  const { isLoggedIn, me } = useAuth();
  const ask = () => {
    if (!isLoggedIn) return router.push({ pathname: '/auth', params: { next: `/experience/${e.id}` } });
    openThreadForBooking(e.id);
  };
  const own = me?.id === e.provider.id;
  const avatar = e.provider.avatar?.urls?.w400;
  return (
    <View style={styles.hostRow}>
      {avatar ? (
        <Image source={avatar} style={styles.avatar} contentFit="cover" />
      ) : (
        <View style={[styles.avatar, styles.avatarFallback]}>
          <Text style={{ color: colors.white, fontWeight: '700', fontSize: 18 }}>{e.provider.display_name[0]}</Text>
        </View>
      )}
      <View style={{ flex: 1, marginLeft: space.md }}>
        <Text style={type.bodyStrong}>{t('detail.host', { name: e.provider.display_name })}</Text>
        {e.provider.is_verified ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 2 }}>
            <Ionicons name="shield-checkmark" size={14} color={colors.success} />
            <Text style={[type.small, { marginLeft: 4 }]}>{t('detail.verified')}</Text>
          </View>
        ) : null}
      </View>
      {!own ? (
        <Pressable onPress={ask} style={styles.ask} accessibilityRole="button" accessibilityLabel={t('inbox.ask')}>
          <Ionicons name="chatbubble-outline" size={18} color={colors.text} />
        </Pressable>
      ) : null}
    </View>
  );
}

function Reviews({ e }: { e: ExperienceDetail }) {
  const { t, i18n } = useTranslation();
  const query = useExperienceReviews(e.id);
  const [reporting, setReporting] = useState<string | null>(null);
  const first = query.data?.pages[0];
  const summary = first?.summary;
  const reviews = query.data?.pages.flatMap((p) => p.results) ?? [];
  return (
    <Section title={t('detail.reviews')}>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: space.md }}>
        <Ionicons name="star" size={18} color={colors.star} />
        <Text style={[type.heading, { marginLeft: 6 }]}>
          {summary?.count ? `${Number(summary.overall).toFixed(2)} · ${t('detail.reviewsCount', { count: summary.count })}` : t('detail.noReviews')}
        </Text>
      </View>
      {summary?.count ? (
        <View style={{ marginBottom: space.lg }}>
          <RatingBar label={t('reviews.learning')} value={summary.learning} />
          <RatingBar label={t('reviews.facilitator')} value={summary.facilitator} />
          <RatingBar label={t('reviews.facilities')} value={summary.facilities} />
        </View>
      ) : null}
      {reviews.map((r) => (
        <View key={r.id} style={styles.review}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <View style={styles.reviewAvatar}><Text style={{ color: colors.white, fontWeight: '700' }}>{r.author[0] ?? '?'}</Text></View>
            <View style={{ flex: 1, marginLeft: space.sm }}>
              <Text style={type.bodyStrong}>{r.author}</Text>
              <Text style={type.caption}>{formatSessionDate(r.date, i18n.language).split(' · ')[0]}</Text>
            </View>
            <Pressable hitSlop={10} onPress={() => setReporting(r.id)} accessibilityLabel={t('reviews.report')}>
              <Ionicons name="ellipsis-horizontal" size={18} color={colors.textMuted} />
            </Pressable>
          </View>
          <View style={{ marginTop: space.sm }}><Stars value={r.overall} size={12} /></View>
          {r.text ? <Text style={[type.body, { marginTop: space.sm }]}>{r.text}</Text> : null}
        </View>
      ))}
      {query.hasNextPage ? <Button title={t('reviews.more')} variant="secondary" onPress={() => query.fetchNextPage()} loading={query.isFetchingNextPage} /> : null}
      {reporting ? <ReportSheet target="review" id={reporting} onClose={() => setReporting(null)} /> : null}
    </Section>
  );
}

function ReportLink({ id }: { id: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Pressable onPress={() => setOpen(true)} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: space.lg }} accessibilityRole="button">
        <Ionicons name="flag-outline" size={16} color={colors.textMuted} />
        <Text style={[type.small, { marginLeft: space.sm, textDecorationLine: 'underline' }]}>{t('report.title.experience')}</Text>
      </Pressable>
      {open ? <ReportSheet target="experience" id={id} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function Upcoming({ e }: { e: ExperienceDetail }) {
  const { t, i18n } = useTranslation();
  const sessions = e.upcoming.sessions ?? [];
  const cohorts = e.upcoming.cohorts ?? [];
  if (!sessions.length && !cohorts.length) return null;
  return (
    <Section title={cohorts.length ? t('detail.cohorts') : t('detail.upcoming')}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.md }}>
        {sessions.map((s) => (
          <View key={s.id} style={styles.dateCard}>
            <Text style={type.bodyStrong}>{formatSessionDate(s.starts_at, i18n.language).split(' · ')[0]}</Text>
            <Text style={type.small}>{formatTimeRange(s.starts_at, s.ends_at, i18n.language)}</Text>
            <Text style={[type.caption, { marginTop: space.sm }]}>{t('detail.seatsLeft', { count: s.seats_left })}</Text>
          </View>
        ))}
        {cohorts.map((c) => (
          <View key={c.id} style={[styles.dateCard, { width: 220 }]}>
            <Text style={type.bodyStrong}>{c.label || formatSessionDate(c.sessions[0].starts_at, i18n.language)}</Text>
            <Text style={type.small}>{t('detail.sessionsCount', { count: c.sessions.length })}</Text>
            {c.sessions.slice(0, 3).map((s) => (
              <Text key={s.starts_at} style={type.caption}>
                {formatSessionDate(s.starts_at, i18n.language)}
              </Text>
            ))}
            <Text style={[type.caption, { marginTop: space.sm }]}>{t('detail.seatsLeft', { count: c.seats_left })}</Text>
          </View>
        ))}
      </ScrollView>
    </Section>
  );
}

function Where({ e }: { e: ExperienceDetail }) {
  const { t } = useTranslation();
  const loc = e.location;
  if (!loc) return null;
  if (loc.online) {
    return (
      <Section title={t('online.where')}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Ionicons name="videocam-outline" size={22} color={colors.text} />
          <Text style={[type.body, { marginLeft: space.md, flex: 1 }]}>{loc.url ?? t('online.whereBody')}</Text>
        </View>
      </Section>
    );
  }
  const region = { latitude: loc.lat, longitude: loc.lng, latitudeDelta: 0.025, longitudeDelta: 0.025 };
  return (
    <Section title={t('detail.where')}>
      <Text style={[type.body, { marginBottom: space.md }]}>{loc.approximate ? e.area ?? '' : loc.address_line}</Text>
      <View style={styles.mapWrap}>
        <MapView
          style={StyleSheet.absoluteFill}
          initialRegion={region}
          scrollEnabled={false}
          zoomEnabled={false}
          pitchEnabled={false}
          rotateEnabled={false}
        >
          {loc.approximate ? (
            <Circle center={region} radius={loc.radius_m} fillColor="rgba(90,49,244,0.15)" strokeColor="rgba(90,49,244,0.6)" />
          ) : (
            <Marker coordinate={region} />
          )}
        </MapView>
      </View>
      {loc.approximate ? <Text style={[type.small, { marginTop: space.sm }]}>{t('detail.approx')}</Text> : null}
    </Section>
  );
}

function SpacePhotos({ e }: { e: ExperienceDetail }) {
  const photos = (e.space?.media ?? []).filter((m) => m.urls).slice(0, 4);
  if (!photos.length) return null;
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md }}>
      {photos.map((m) => (
        <Image
          key={m.id}
          source={m.urls?.w400}
          style={{ width: '48%', aspectRatio: 1, borderRadius: radius.md, backgroundColor: m.color }}
        />
      ))}
    </View>
  );
}

function AboutHost({ e }: { e: ExperienceDetail }) {
  const { t } = useTranslation();
  const text = [e.provider.about_me, e.provider.about_school].filter(Boolean).join('\n\n');
  if (!text) return null;
  return (
    <Section title={t('detail.aboutHost')}>
      <Text style={type.body}>{text}</Text>
    </Section>
  );
}

function BookingBar({ e, bottom }: { e: ExperienceDetail; bottom: number }) {
  const { t, i18n } = useTranslation();
  const { isLoggedIn, me } = useAuth();
  const onBook = () => {
    const next = `/experience/${e.id}`;
    if (!isLoggedIn) return router.push({ pathname: '/auth', params: { next } });
    if (!me?.profile_complete) return router.push({ pathname: '/auth/complete-profile', params: { next } });
    router.push(`/book/${e.id}`);
  };
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(bottom, space.md) }]}>
      <View style={{ flex: 1, paddingRight: space.md }}>
        <Text style={type.bodyStrong}>
          {formatMoney(e.price.total_cents, i18n.language)} MXN{' '}
          <Text style={{ fontWeight: '400', color: colors.textMuted }}>{t('feed.total')}</Text>
        </Text>
        <Text style={type.caption} numberOfLines={2}>
          {t('detail.priceNote')}
        </Text>
      </View>
      <Button title={t('detail.book')} onPress={onBook} style={{ minWidth: 140 }} />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  body: {
    paddingHorizontal: space.xl,
    marginTop: -radius.xl,
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  back: {
    position: 'absolute',
    left: space.lg,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.white,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hostRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.xl,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.hairline,
  },
  avatar: { width: 48, height: 48, borderRadius: 24 },
  ask: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  review: { paddingVertical: space.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline },
  reviewAvatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.text, alignItems: 'center', justifyContent: 'center' },
  avatarFallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: colors.text },
  dateCard: { width: 150, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: space.md },
  mapWrap: { height: 200, borderRadius: radius.lg, overflow: 'hidden' },
  bar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.xl,
    paddingTop: space.md,
    backgroundColor: colors.bg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.hairline,
  },
});
