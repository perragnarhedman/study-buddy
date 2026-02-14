## iOS: First TestFlight build (setup + checklist)

This guide is meant to get you from “repo builds locally in Xcode” to “I can install it on my iPhone via TestFlight”.

### 1) Apple accounts you need

- **Apple Developer Program** membership (paid) for the team that will ship the app
- **App Store Connect** access for that same team

#### Recommended roles (App Store Connect)

- **Admin** (best) or **App Manager** (usually sufficient)
- **Developer** for uploading builds is often enough, but you still need someone with app-creation rights

### 2) Bundle ID (must be unique)

Apple requires a unique **Bundle Identifier**.

Current repo value (in Xcode project settings):
- `PRODUCT_BUNDLE_IDENTIFIER = com.example.StudyBuddyApp`
- File: `ios/StudyBuddyApp/StudyBuddyApp.xcodeproj/project.pbxproj`

Before creating the app in App Store Connect, decide the final bundle id (example format):
- `com.<yourname-or-company>.StudyBuddyApp`

### 3) Create the app record in App Store Connect

In **App Store Connect → Apps → + → New App**:
- **Platform**: iOS
- **Name**: Study Buddy (or your final product name)
- **Primary language**: Swedish or English (your choice; this does not auto-localize UI)
- **Bundle ID**: select the one matching Xcode
- **SKU**: any unique string (example: `studybuddy-ios-001`)

### 4) Xcode signing (first time)

In Xcode:
1. Open: `ios/StudyBuddyApp/StudyBuddyApp.xcodeproj`
2. Select target **StudyBuddyApp**
3. Go to **Signing & Capabilities**
4. Set:
   - **Team**: your Apple Developer team
   - **Automatically manage signing**: ON

Verify on device:
- Plug in your iPhone
- Select your device as the run target
- Build/Run once (this ensures the signing chain is correct)

### 5) Upload first build to TestFlight

1. In Xcode: **Product → Archive**
2. In the Organizer window: **Distribute App**
3. Choose **App Store Connect** (upload)
4. Follow the prompts to upload

In App Store Connect:
- Go to **TestFlight**
- Wait for build processing (can take a while)
- Add yourself as an **Internal Tester**
- Install via the TestFlight app on your iPhone

### Acceptance checklist

- You can **install the build on your iPhone** via TestFlight
- App launches successfully
- You can reach the backend if base URL is set (or use stub mode)


