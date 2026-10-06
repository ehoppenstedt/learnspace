import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ApiError } from '@/lib/api/client';
import { AuthProvider } from '@/lib/auth/AuthContext';
import { restoreLanguage } from '@/lib/i18n'; // also initializes i18next
import { FiltersProvider } from '@/lib/state/FiltersContext';
import { LocationProvider } from '@/lib/state/LocationContext';
import { colors } from '@/theme/tokens';

export default function RootLayout() {
  const { t } = useTranslation();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Don't hammer the API on 4xx; retry network/5xx twice.
            retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
          },
        },
      }),
  );
  useEffect(() => {
    restoreLanguage();
  }, []);

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <LocationProvider>
            <FiltersProvider>
              <StatusBar style="dark" />
              <Stack
                screenOptions={{
                  headerShadowVisible: false,
                  headerTintColor: colors.text,
                  headerBackButtonDisplayMode: 'minimal',
                  contentStyle: { backgroundColor: colors.bg },
                }}
              >
                <Stack.Screen name="index" options={{ headerShown: false }} />
                <Stack.Screen name="experience/[id]" options={{ headerShown: false }} />
                <Stack.Screen name="filters" options={{ presentation: 'modal', title: t('filters.title') }} />
                <Stack.Screen name="location" options={{ presentation: 'modal', title: t('location.title') }} />
                <Stack.Screen name="menu" options={{ presentation: 'transparentModal', headerShown: false, animation: 'fade' }} />
                <Stack.Screen name="auth" options={{ presentation: 'modal', headerShown: false }} />
                <Stack.Screen name="profile/index" options={{ title: t('profile.title') }} />
                <Stack.Screen name="profile/interests" options={{ title: t('profile.interests') }} />
                <Stack.Screen name="provider/index" options={{ title: t('provider.myExperiences') }} />
                <Stack.Screen name="provider/become" options={{ title: '' }} />
                <Stack.Screen name="provider/experience/[id]" options={{ title: '' }} />
                <Stack.Screen name="provider/sessions/[id]" options={{ title: t('sessions.title') }} />
                <Stack.Screen name="provider/space" options={{ presentation: 'modal', title: t('space.title') }} />
              </Stack>
            </FiltersProvider>
          </LocationProvider>
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
