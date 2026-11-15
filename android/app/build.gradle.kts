plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing comes from the environment (GitHub Actions secrets), so no
// key or password is ever committed. See .github/workflows/android-release.yml.
val releaseKeystore: String? = System.getenv("XCURS_KEYSTORE")

android {
    namespace = "io.github.ayush00git.xcurs"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.ayush00git.xcurs"
        minSdk = 26
        targetSdk = 35
        versionCode = System.getenv("XCURS_VERSION_CODE")?.toIntOrNull() ?: 2
        versionName = System.getenv("XCURS_VERSION") ?: "0.5.0"
    }

    signingConfigs {
        create("release") {
            if (releaseKeystore != null) {
                storeFile = file(releaseKeystore)
                storePassword = System.getenv("XCURS_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("XCURS_KEY_ALIAS")
                keyPassword = System.getenv("XCURS_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Without a release key (e.g. a local build) fall back to the debug
            // key, so the APK still installs.
            signingConfig = signingConfigs.getByName(if (releaseKeystore != null) "release" else "debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.3")
    // The QR scanner pulls in an old Fragment; ActivityResult APIs need 1.3+.
    implementation("androidx.fragment:fragment-ktx:1.8.5")
    // Google's QR scanner UI: no camera permission, no camera code in our app.
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")

    testImplementation("junit:junit:4.13.2")
}
