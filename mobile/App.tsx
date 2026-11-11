import React from 'react';
import { emailLinking } from './src/emailLinks';
import { recordAction } from './src/activity';
import ResourceSettingsScreen from './src/screens/ResourceSettingsScreen';
import FriendProfileScreen from './src/screens/FriendProfileScreen';
import { ActivityIndicator } from 'react-native';
import { DarkTheme, NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { colors } from './src/ui';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { BottomTabBar, createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View } from 'react-native';
import { MiniPlayer, PlayerProvider } from './src/music/player';
import { AuthProvider, useAuth } from './src/context/AuthContext';
import { SubscriptionProvider } from './src/context/SubscriptionContext';
import SubscriptionScreen from './src/screens/SubscriptionScreen';
import LoginScreen from './src/screens/LoginScreen';
import RegisterScreen from './src/screens/RegisterScreen';
import VerifyEmailScreen from './src/screens/VerifyEmailScreen';
import ResetPasswordScreen from './src/screens/ResetPasswordScreen';
import GoogleAuthScreen from './src/screens/GoogleAuthScreen';
import EventsScreen from './src/screens/EventsScreen';
import EventDetailScreen from './src/screens/EventDetailScreen';
import PlaylistsScreen from './src/screens/PlaylistsScreen';
import PlaylistDetailScreen from './src/screens/PlaylistDetailScreen';
import DelegationScreen from './src/screens/DelegationScreen';
import FriendsScreen from './src/screens/FriendsScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import OfflineScreen from './src/screens/OfflineScreen';
import NearbyScreen from './src/screens/NearbyScreen';

import { NearbyProvider, NearbyBanner } from './src/context/NearbyContext';
const navigationRef = createNavigationContainerRef<any>();

const Stack = createNativeStackNavigator();
const Tabs = createBottomTabNavigator();

const theme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: colors.bg, card: colors.bg, text: colors.text, primary: colors.accent, border: colors.surface },
};
const stackOptions = { headerStyle: { backgroundColor: colors.bg }, headerTintColor: colors.text, headerShadowVisible: false };

const icons: Record<string, [keyof typeof Ionicons.glyphMap, keyof typeof Ionicons.glyphMap]> = {
  Vote: ['flame', 'flame-outline'],
  Playlists: ['library', 'library-outline'],
  Delegation: ['people', 'people-outline'],
  Friends: ['heart', 'heart-outline'],
  Profile: ['person', 'person-outline'],
};

function MainTabs() {
  return (
    <Tabs.Navigator tabBar={(props) => <View><MiniPlayer /><BottomTabBar {...props} /></View>}
      screenOptions={({ route }) => ({
      ...stackOptions,
      tabBarActiveTintColor: colors.text,
      tabBarInactiveTintColor: colors.muted,
      tabBarStyle: { backgroundColor: colors.bg, borderTopColor: colors.surface },
      tabBarIcon: ({ focused, color, size }) => <Ionicons name={icons[route.name][focused ? 0 : 1]} size={size} color={focused ? colors.accent : color} />,
    })}>
      <Tabs.Screen name="Vote" component={EventsScreen} options={{ title: 'Live' }} />
      <Tabs.Screen name="Playlists" component={PlaylistsScreen} options={{ title: 'Library' }} />
      <Tabs.Screen name="Delegation" component={DelegationScreen} options={{ title: 'Control' }} />
      <Tabs.Screen name="Friends" component={FriendsScreen} />
      <Tabs.Screen name="Profile" component={ProfileScreen} />
    </Tabs.Navigator>
  );
}

export function Root() {
  const { user, ready } = useAuth();
  if (!ready) return <ActivityIndicator style={{ flex: 1, backgroundColor: colors.bg }} color={colors.accent} />;
  return (
    <Stack.Navigator key={user?.id ?? 'anonymous'} initialRouteName={user ? 'Main' : 'Login'} screenOptions={stackOptions}>
      {user ? (
        <>
          <Stack.Screen name="Main" component={MainTabs} options={{ headerShown: false }} />
          <Stack.Screen name="ResourceSettings" component={ResourceSettingsScreen} options={{ title: 'Service settings' }} />
          <Stack.Screen name="FriendProfile" component={FriendProfileScreen} options={{ title: 'Friend profile' }} />
          <Stack.Screen name="EventDetail" component={EventDetailScreen} options={{ title: 'Event' }} />
          <Stack.Screen name="PlaylistDetail" component={PlaylistDetailScreen} options={{ title: 'Playlist' }} />
          <Stack.Screen name="LinkGoogle" initialParams={{ intent: 'link' }} component={GoogleAuthScreen} options={{ title: 'Link Google' }} />
          <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Backend settings' }} />
          <Stack.Screen name="Plans" component={SubscriptionScreen} options={{ title: 'Plans' }} />
          <Stack.Screen name="Offline" component={OfflineScreen} options={{ title: 'Offline playlists' }} />
          <Stack.Screen name="Nearby" component={NearbyScreen} options={{ title: 'Nearby events' }} />
        </>
      ) : (
        <>
          <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
          <Stack.Screen name="Register" component={RegisterScreen} />
          <Stack.Screen name="VerifyEmail" component={VerifyEmailScreen} options={{ title: 'Verify email' }} />
          <Stack.Screen name="ResetPassword" component={ResetPasswordScreen} options={{ title: 'Reset password' }} />
          <Stack.Screen navigationKey={user ? "signed-in" : "signed-out"} name="GoogleAuth" component={GoogleAuthScreen} options={{ title: 'Google sign-in' }} />
          <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Backend settings' }} />
        </>
      )}
    </Stack.Navigator>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <SubscriptionProvider>
      <NearbyProvider><PlayerProvider>
        <NavigationContainer ref={navigationRef} linking={emailLinking} theme={theme} onStateChange={() => recordAction('screen_view')}><StatusBar style="light" /><View style={{ flex: 1 }}><NearbyBanner open={event => { if (navigationRef.isReady()) navigationRef.navigate("EventDetail", { id: event.id, name: event.name }); }} /><Root /></View></NavigationContainer>
      </PlayerProvider></NearbyProvider>
      </SubscriptionProvider>
    </AuthProvider>
  );
}
