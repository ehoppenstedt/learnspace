import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Alert, FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ReportSheet } from '@/components/ReportSheet';
import { ApiError, api } from '@/lib/api/client';
import { useThreadMessages } from '@/lib/api/hooks';
import type { ChatMessage, ReportTarget } from '@/lib/api/types';
import { formatRelative } from '@/lib/utils/format';
import { colors, radius, space, type } from '@/theme/tokens';

export default function ThreadScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const query = useThreadMessages(id);
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [report, setReport] = useState<{ target: ReportTarget; id: string } | null>(null);
  const list = useRef<FlatList<ChatMessage>>(null);
  const thread = query.data?.thread;
  const messages = query.data?.messages ?? [];

  useEffect(() => {
    // Opening the thread marks it read on the server; refresh badges.
    if (query.data) qc.invalidateQueries({ queryKey: ['threads'] });
  }, [query.data?.messages.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (acknowledged = false) => {
    const text = body.trim();
    if (!text) return;
    setSending(true);
    try {
      await api(`/threads/${id}/messages`, { method: 'POST', body: { body: text, acknowledged_warning: acknowledged } });
      setBody('');
      await query.refetch();
      list.current?.scrollToEnd({ animated: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'contact_info_warning') {
        const kinds = (err.fields.detected as string[] | undefined) ?? [];
        const found = kinds.map((k) => t(`inbox.detected.${k}`)).join(', ');
        Alert.alert(t('inbox.warnTitle'), `${err.message}${found ? `\n\n(${found})` : ''}`, [
          { text: t('inbox.warnEdit'), style: 'cancel' },
          { text: t('inbox.warnSend'), style: 'destructive', onPress: () => send(true) },
        ]);
      } else {
        Alert.alert(err instanceof ApiError ? err.message : t('errors.network'));
      }
    } finally {
      setSending(false);
    }
  };

  if (!thread) return <ActivityIndicator style={{ marginTop: 80 }} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['bottom']}>
      <Stack.Screen options={{
        title: thread.counterpart,
        headerRight: () => (
          <Pressable hitSlop={10} accessibilityLabel={t('inbox.report')} onPress={() => setReport({ target: 'user', id: thread.counterpart_id })}>
            <Ionicons name="flag-outline" size={20} color={colors.text} />
          </Pressable>
        ),
      }} />
      <Pressable style={styles.context} onPress={() => router.push(thread.booking_id && thread.role === 'learner' ? `/bookings/${thread.booking_id}` : `/experience/${thread.experience.id}`)}>
        <Text style={type.smallStrong} numberOfLines={1}>{thread.experience.title}</Text>
        {!thread.booked ? <Text style={type.caption}>{t('inbox.safety')}</Text> : <Text style={type.caption}>{t('inbox.booked')}</Text>}
      </Pressable>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
        <FlatList
          ref={list}
          data={messages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{ padding: space.lg }}
          onContentSizeChange={() => list.current?.scrollToEnd({ animated: false })}
          renderItem={({ item }) => (
            <Pressable
              onLongPress={() => !item.mine && setReport({ target: 'message', id: item.id })}
              style={[styles.bubble, item.mine ? styles.mine : styles.theirs]}
              accessibilityHint={!item.mine ? t('report.title.message') : undefined}
            >
              <Text style={[type.body, item.mine && { color: colors.white }]}>{item.body}</Text>
              <Text style={[type.caption, { marginTop: 2, textAlign: 'right' }, item.mine && { color: 'rgba(255,255,255,0.75)' }]}>
                {item.flagged ? `${t('inbox.flagged')} · ` : ''}{formatRelative(item.at, i18n.language)}
              </Text>
            </Pressable>
          )}
        />
        <View style={styles.composer}>
          <TextInput
            value={body}
            onChangeText={setBody}
            placeholder={t('inbox.placeholder')}
            placeholderTextColor={colors.textSubtle}
            multiline
            maxLength={2000}
            style={styles.input}
            accessibilityLabel={t('inbox.placeholder')}
          />
          <Pressable onPress={() => send(false)} disabled={sending || !body.trim()} style={[styles.send, (!body.trim() || sending) && { opacity: 0.4 }]}
            accessibilityRole="button" accessibilityLabel={t('inbox.send')}>
            {sending ? <ActivityIndicator color={colors.white} /> : <Ionicons name="arrow-up" size={20} color={colors.white} />}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
      {report ? (
        <ReportSheet target={report.target} id={report.id} onClose={() => setReport(null)} />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  context: { paddingHorizontal: space.xl, paddingVertical: space.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.hairline, backgroundColor: colors.surface },
  bubble: { maxWidth: '80%', borderRadius: radius.lg, paddingHorizontal: space.md, paddingVertical: space.sm, marginBottom: space.sm },
  mine: { alignSelf: 'flex-end', backgroundColor: colors.text, borderBottomRightRadius: 4 },
  theirs: { alignSelf: 'flex-start', backgroundColor: colors.surface, borderBottomLeftRadius: 4 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', padding: space.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.hairline },
  input: { flex: 1, minHeight: 44, maxHeight: 120, borderWidth: 1, borderColor: colors.border, borderRadius: 22, paddingHorizontal: space.lg, paddingTop: 12, paddingBottom: 12, fontSize: 16, color: colors.text },
  send: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center', marginLeft: space.sm },
});
