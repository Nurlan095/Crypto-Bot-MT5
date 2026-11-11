package com.nurik.cryptobot;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.media.AudioManager;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.media.ToneGenerator;
import android.net.Uri;
import android.graphics.Insets;
import android.os.Build;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.provider.Settings;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {

    private static final String CHANNEL_ID = "crypto_bot_silent_v266";
    private static final String PREFS_NAME = "CryptoBotPrefs";
    private static final int REQ_INSTALL_PERMISSION = 202;
    private WebView webView;
    private int notifCounter = 1001;
    private boolean pendingApkInstall = false;

    private int dpToPx(int dp) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(dp * density);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(Color.parseColor("#0B0F17"));
        window.setNavigationBarColor(Color.parseColor("#0B0F17"));

        createNotificationChannel();
        requestNotificationPermissionIfNeeded();

        final int minTopPx = dpToPx(28);
        final int minBottomPx = dpToPx(48);

        FrameLayout rootLayout = new FrameLayout(this);
        rootLayout.setBackgroundColor(Color.parseColor("#0B0F17"));
        rootLayout.setPadding(0, minTopPx, 0, minBottomPx);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#0B0F17"));

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowUniversalAccessFromFileURLs(true);
        settings.setAllowFileAccessFromFileURLs(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient());
        webView.addJavascriptInterface(new AndroidBridge(this), "AndroidBridge");

        rootLayout.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT_WATCH) {
            rootLayout.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
                @Override
                public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                        Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                        v.setPadding(
                                bars.left,
                                Math.max(bars.top, minTopPx),
                                bars.right,
                                Math.max(bars.bottom, minBottomPx)
                        );
                    } else {
                        v.setPadding(
                                insets.getSystemWindowInsetLeft(),
                                Math.max(insets.getSystemWindowInsetTop(), minTopPx),
                                insets.getSystemWindowInsetRight(),
                                Math.max(insets.getSystemWindowInsetBottom(), minBottomPx)
                        );
                    }
                    return insets;
                }
            });
        }

        setContentView(rootLayout);
        webView.loadUrl("file:///android_asset/index.html");
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Crypto Bot Тихие Уведомления",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Тихие уведомления о сделках без резкого звука");
            channel.setSound(null, null);
            channel.enableVibration(false);
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 101);
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_INSTALL_PERMISSION && pendingApkInstall) {
            pendingApkInstall = false;
            installDownloadedApk();
        }
    }

    private void notifyJsUpdateStatus(final String statusText) {
        if (webView != null) {
            final String safe = statusText.replace("'", "\\'");
            webView.post(() -> webView.evaluateJavascript(
                    "if(window.onApkUpdateStatus) window.onApkUpdateStatus('" + safe + "');",
                    null
            ));
        }
    }

    private void installDownloadedApk() {
        try {
            File apkFile = new File(getExternalFilesDir(null), "Crypto_Bot_Update.apk");
            if (!apkFile.exists()) {
                notifyJsUpdateStatus("Ошибка: файл обновления не найден");
                return;
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (!getPackageManager().canRequestPackageInstalls()) {
                    pendingApkInstall = true;
                    notifyJsUpdateStatus("Разрешите установку обновлений в открывшемся окне...");
                    Intent permIntent = new Intent(
                            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:" + getPackageName())
                    );
                    startActivityForResult(permIntent, REQ_INSTALL_PERMISSION);
                    return;
                }
            }

            notifyJsUpdateStatus("Запуск установщика обновления...");
            Uri apkUri = Uri.parse("content://" + ApkFileProvider.AUTHORITY + "/Crypto_Bot_Update.apk");
            Intent installIntent = new Intent(Intent.ACTION_VIEW);
            installIntent.setDataAndType(apkUri, "application/vnd.android.package-archive");
            installIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(installIntent);
        } catch (Exception e) {
            notifyJsUpdateStatus("Ошибка установки: " + e.getMessage());
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    public class AndroidBridge {
        private final Context context;
        private final SharedPreferences prefs;

        public AndroidBridge(Context ctx) {
            this.context = ctx;
            this.prefs = ctx.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        }

        @JavascriptInterface
        public int getAppVersionCode() {
            try {
                PackageInfo pInfo = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    return (int) pInfo.getLongVersionCode();
                }
                return pInfo.versionCode;
            } catch (Exception e) {
                return 250;
            }
        }

        @JavascriptInterface
        public String getAppVersionName() {
            try {
                PackageInfo pInfo = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
                return pInfo.versionName;
            } catch (Exception e) {
                return "2.50";
            }
        }

        @JavascriptInterface
        public void downloadAndInstallApk(final String apkUrl) {
            downloadAndInstallUpdate(apkUrl);
        }

        @JavascriptInterface
        public void downloadAndInstallUpdate(final String apkUrl) {
            new Thread(() -> {
                HttpURLConnection conn = null;
                try {
                    notifyJsUpdateStatus("Скачивание новой версии с сервера...");
                    String sep = apkUrl.contains("?") ? "&" : "?";
                    URL url = new URL(apkUrl + sep + "t=" + System.currentTimeMillis());
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("GET");
                    conn.setConnectTimeout(15000);
                    conn.setReadTimeout(30000);
                    conn.setUseCaches(false);
                    conn.setRequestProperty("Cache-Control", "no-cache");

                    int code = conn.getResponseCode();
                    if (code < 200 || code >= 300) {
                        notifyJsUpdateStatus("Ошибка загрузки (HTTP " + code + ")");
                        return;
                    }

                    int contentLength = conn.getContentLength();
                    File outFile = new File(context.getExternalFilesDir(null), "Crypto_Bot_Update.apk");
                    try (InputStream is = conn.getInputStream();
                         FileOutputStream fos = new FileOutputStream(outFile)) {
                        byte[] buf = new byte[8192];
                        int n;
                        int total = 0;
                        int lastPct = -1;
                        while ((n = is.read(buf)) != -1) {
                            fos.write(buf, 0, n);
                            total += n;
                            if (contentLength > 0) {
                                final int pct = Math.min(99, (int) ((total * 100L) / contentLength));
                                if (pct != lastPct && webView != null) {
                                    lastPct = pct;
                                    webView.post(() -> webView.evaluateJavascript(
                                            "if(window.onApkDownloadProgress) window.onApkDownloadProgress(" + pct + ");",
                                            null
                                    ));
                                }
                            }
                        }
                        fos.flush();
                    }
                    if (webView != null) {
                        webView.post(() -> webView.evaluateJavascript(
                                "if(window.onApkDownloadProgress) window.onApkDownloadProgress(100);",
                                null
                        ));
                    }
                    notifyJsUpdateStatus("Файл загружен! Открываем обновление...");
                    runOnUiThread(() -> installDownloadedApk());
                } catch (Exception e) {
                    notifyJsUpdateStatus("Ошибка скачивания: " + e.getMessage());
                } finally {
                    if (conn != null) conn.disconnect();
                }
            }).start();
        }

        @JavascriptInterface
        public void playAlertSound() {
            if ("1".equals(prefs.getString("sound_muted", "1"))) {
                return;
            }
            try {
                Uri soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
                Ringtone r = RingtoneManager.getRingtone(context, soundUri);
                if (r != null) r.play();
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void sendNotification(String title, String message) {
            playAlertSound();
            try {
                NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
                if (manager == null) return;

                Intent intent = new Intent(context, MainActivity.class);
                intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                int flags = PendingIntent.FLAG_UPDATE_CURRENT;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    flags |= PendingIntent.FLAG_IMMUTABLE;
                }
                PendingIntent pendingIntent = PendingIntent.getActivity(context, 0, intent, flags);

                Notification.Builder builder;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    builder = new Notification.Builder(context, CHANNEL_ID);
                } else {
                    builder = new Notification.Builder(context);
                    builder.setPriority(Notification.PRIORITY_LOW);
                }

                builder.setContentTitle(title)
                        .setContentText(message)
                        .setSmallIcon(android.R.drawable.stat_notify_more)
                        .setAutoCancel(true)
                        .setContentIntent(pendingIntent);

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN) {
                    builder.setStyle(new Notification.BigTextStyle().bigText(message));
                    manager.notify(notifCounter++, builder.build());
                }
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void savePref(String key, String value) {
            prefs.edit().putString(key, value).apply();
        }

        @JavascriptInterface
        public String getPref(String key, String defVal) {
            return prefs.getString(key, defVal);
        }

        @JavascriptInterface
        public String httpGet(String urlStr) {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(urlStr);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);
                conn.setUseCaches(false);
                conn.setRequestProperty("Accept", "application/json");
                conn.setRequestProperty("Cache-Control", "no-cache");
                int code = conn.getResponseCode();
                if (code >= 200 && code < 300) {
                    BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        sb.append(line);
                    }
                    reader.close();
                    return sb.toString();
                }
            } catch (Exception ignored) {
            } finally {
                if (conn != null) conn.disconnect();
            }
            return "";
        }

        @JavascriptInterface
        public String httpPost(String urlStr, String jsonBody) {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(urlStr);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                byte[] input = jsonBody.getBytes(StandardCharsets.UTF_8);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(input, 0, input.length);
                }
                int code = conn.getResponseCode();
                if (code >= 200 && code < 300) {
                    BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        sb.append(line);
                    }
                    reader.close();
                    return sb.toString();
                }
            } catch (Exception ignored) {
            } finally {
                if (conn != null) conn.disconnect();
            }
            return "";
        }
    }
}
