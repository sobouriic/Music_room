import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
// The SDK-57 barrel eagerly imports remote topic subscriptions missing in Expo Go.
// Load only local APIs from the pinned package; no push tokens/topics are needed.
type LocalNotifications = Pick<typeof import('expo-notifications'),
  'setNotificationHandler' | 'setNotificationChannelAsync' | 'requestPermissionsAsync'
  | 'scheduleNotificationAsync' | 'AndroidImportance' | 'getPermissionsAsync'>;
function notifications(): LocalNotifications {
  try {
    const handler: typeof import('expo-notifications/build/NotificationsHandler') = require('expo-notifications/build/NotificationsHandler');
    const channels: typeof import('expo-notifications/build/setNotificationChannelAsync') = require('expo-notifications/build/setNotificationChannelAsync');
    const permissions: typeof import('expo-notifications/build/NotificationPermissions') = require('expo-notifications/build/NotificationPermissions');
    const scheduler: typeof import('expo-notifications/build/scheduleNotificationAsync') = require('expo-notifications/build/scheduleNotificationAsync');
    const types: typeof import('expo-notifications/build/NotificationChannelManager.types') = require('expo-notifications/build/NotificationChannelManager.types');
    return {
      setNotificationHandler: handler.setNotificationHandler,
      setNotificationChannelAsync: channels.setNotificationChannelAsync,
      requestPermissionsAsync: permissions.requestPermissionsAsync,
      getPermissionsAsync: permissions.getPermissionsAsync,
      scheduleNotificationAsync: scheduler.scheduleNotificationAsync,
      AndroidImportance: types.AndroidImportance,
    };
  } catch {
    throw new Error('Phone notifications are unavailable in this installed app. Rebuild Music Room with make android-build or make ios-build, then use make android or make ios.');
  }
}
import { loadConfig } from './config';
import { VoteEvent } from './api/types';

// Expo Go may expose the channel API without its SDK-57 provider. Its default
// local-notification channel is created by the native notification builder.
let androidChannel: string | undefined;
export async function enableNearbyNotifications(request = true): Promise<boolean> {
  androidChannel = undefined;
  try {
    const Notifications = notifications();
    Notifications.setNotificationHandler({ handleNotification: async () => ({
      shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false,
    }) });
    if (Platform.OS === 'android' && Constants.executionEnvironment !== 'storeClient') {
      try {
        await Notifications.setNotificationChannelAsync('nearby-events-visible-v2', {
          name: 'Nearby public events', importance: Notifications.AndroidImportance.HIGH, sound: 'default', vibrationPattern: [0, 250, 200, 250],
        });
        androidChannel = 'nearby-events-visible-v2';
      } catch {
        // Missing channel providers must not block permissions or nearby discovery.
        // Scheduling with trigger:null uses the runtime's built-in default channel.
      }
    }
    return (await (request ? Notifications.requestPermissionsAsync() : Notifications.getPermissionsAsync())).granted;
  } catch {
    // This is optional: the screen keeps location discovery enabled without alerts.
    return false;
  }
}

export async function showNearbyAlerts(userId: string, events: VoteEvent[]): Promise<void> {
  const Notifications = notifications();
  const key = `music-room-nearby-alerts:${(await loadConfig()).baseUrl}:${userId}`;
  let seen: Record<string, number> = {};
  try { seen = JSON.parse(await AsyncStorage.getItem(key) ?? '{}'); } catch {}
  const now = Date.now();
  // Deduplicate for 30 minutes, including after closing/reopening the screen.
  seen = Object.fromEntries(Object.entries(seen).filter(([, time]) => time > now - 1800000));
  for (const event of events.slice(0, 30)) {
    if (seen[event.id]) continue;
    try { await Notifications.scheduleNotificationAsync({
      content: { title: 'Music Room event nearby', body: event.name,
        data: { eventId: event.id }, sound: 'default' },
      trigger: Platform.OS === 'android' && androidChannel ? { channelId: androidChannel } : null,
    }); } catch {
      throw new Error('Phone notification could not be displayed. Check notification permissions or use the Music Room development app. Nearby results remain available.');
    }
    seen[event.id] = now;
    // Persist each acknowledgment so a later scheduling error does not duplicate earlier alerts.
    await AsyncStorage.setItem(key, JSON.stringify(seen));
  }
}
