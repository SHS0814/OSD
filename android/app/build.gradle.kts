plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "kr.ac.cbnu.campusshade"
    compileSdk = 35

    defaultConfig {
        applicationId = "kr.ac.cbnu.campusshade"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        val apiBaseUrl = providers.gradleProperty("API_BASE_URL")
            .orElse("http://10.0.2.2:8000/")
            .get()
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
    }

    buildFeatures {
        buildConfig = true
        viewBinding = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("com.google.android.material:material:1.12.0")
    implementation("org.maplibre.gl:android-sdk-opengl:13.4.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}

