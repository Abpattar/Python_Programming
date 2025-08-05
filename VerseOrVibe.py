import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
import re

# --- CONFIGURATION ---
SCOPE = "user-library-read playlist-modify-public playlist-modify-private"

# Playlist names to process (change these to match your playlists)
SOURCE_PLAYLIST_NAME = "International Songs"  # Change this to process different playlist
LYRICAL_PLAYLIST_NAME = f"{SOURCE_PLAYLIST_NAME} - 🎤 Lyrical"
NON_LYRICAL_PLAYLIST_NAME = f"{SOURCE_PLAYLIST_NAME} - 🎵 Instrumental"

# --- ENHANCED DETECTION KEYWORDS ---
# Strong indicators of instrumental music (international focus)
STRONG_INSTRUMENTAL_KEYWORDS = [
    'instrumental', 'karaoke', 'backing track', 'playback', 'music box',
    'orchestral', 'symphony', 'concerto', 'sonata', 'prelude', 'etude',
    'interlude', 'intro', 'outro', 'overture', 'finale', 'movement',
    'ambient', 'cinematic', 'soundtrack', 'film score', 'movie theme',
    'piano solo', 'guitar solo', 'violin solo', 'saxophone solo', 'drum solo',
    'acoustic guitar', 'classical guitar', 'jazz instrumental',
    'without vocals', 'no vocals', 'vocals removed', 'minus one',
    'meditation music', 'background music', 'study music', 'relaxing music',
    'lofi instrumental', 'chillhop instrumental', 'beats to study','ost','original soundtrack'
]

# Medium confidence instrumental indicators
MEDIUM_INSTRUMENTAL_KEYWORDS = [
    'theme', 'score', 'suite', 'variations', 'improvisation', 'jam',
    'acoustic', 'unplugged version', 'demo version', 'rehearsal',
    'live recording', 'studio session', 'soundscape', 'atmosphere'
]

# Strong indicators of vocal/lyrical music
STRONG_VOCAL_KEYWORDS = [
    'vocals', 'singer', 'sung by', 'featuring', 'ft.', 'feat.',
    'duet', 'chorus', 'verse', 'lyrics', 'ballad', 'anthem',
    'acoustic version', 'live version', 'cover version', 'remix',
    'radio edit', 'single version', 'album version', 'extended version'
]

# Genre-based classification (more accurate for international music)
INSTRUMENTAL_GENRES = [
    'ambient', 'classical', 'instrumental', 'soundtrack', 'score',
    'new age', 'meditation', 'nature sounds', 'white noise',
    'jazz fusion', 'smooth jazz instrumental', 'classical crossover',
    'post-rock', 'math rock', 'experimental', 'drone',
    'minimal techno', 'deep house instrumental', 'trance instrumental',
    'lo-fi beats', 'chillhop', 'downtempo', 'trip-hop instrumental'
]

VOCAL_GENRES = [
    'pop', 'rock', 'hip hop', 'rap', 'r&b', 'soul', 'funk', 'disco',
    'country', 'folk', 'indie pop', 'indie rock', 'alternative',
    'punk', 'metal', 'blues', 'reggae', 'ska', 'gospel',
    'singer-songwriter', 'acoustic pop', 'vocal jazz', 'cabaret'
]

# Artist types that are typically instrumental
INSTRUMENTAL_ARTIST_TYPES = [
    'orchestra', 'symphony', 'philharmonic', 'ensemble', 'quartet', 'trio',
    'band', 'collective', 'project', 'soundsystem', 'beats', 'productions'
]

# Common instrumental track name patterns
INSTRUMENTAL_PATTERNS = [
    r'\b(instrumental|karaoke|backing|playback)\b',
    r'\b(without|minus|no)\s+(vocals?|voice|singing)\b',
    r'\b(piano|guitar|violin|saxophone|drums?|bass)\s+(solo|version|instrumental)\b',
    r'\b(theme|score|soundtrack|ost)\b',
    r'\b(movement|part)\s+\d+\b',  # Classical music movements
    r'\b(prelude|interlude|outro|intro)\b',
    r'\b(ambient|cinematic|atmospheric)\b',
    r'\b(study|focus|concentration|meditation)\s+(music|beats)\b',
    r'\b(lofi|lo-fi|chill)\s+(beats|hip hop|instrumental)\b',
    r'\(instrumental\)|\[instrumental\]',
    r'\(no vocals?\)|\[no vocals?\]',
    r'\(acoustic\)|\[acoustic\]'  # Often instrumental versions
]

# Patterns that suggest vocals
VOCAL_PATTERNS = [
    r'\b(vocals?|singer|sung)\b',
    r'\b(feat\.?|featuring|ft\.?|with)\s+[\w\s]+\b',
    r'\b(cover|version)\s+by\b',
    r'\b(radio|single|album|extended)\s+(edit|version|mix)\b',
    r'\(.*vocals?\)',
    r'\[.*vocals?\]'
]

# --- RATE LIMIT HANDLER ---
def safe_sp_call(callable_func, *args, **kwargs):
    """Handle Spotify API rate limits gracefully"""
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            return callable_func(*args, **kwargs)
        except SpotifyException as e:
            if e.http_status == 429:
                retry_after = int(e.headers.get("Retry-After", 5))
                print(f"⚠️ Rate limit hit. Waiting for {retry_after} seconds... (Attempt {retry_count + 1}/{max_retries})")
                time.sleep(retry_after + 1)
                retry_count += 1
            else:
                print(f"❌ Spotify API error: {e}")
                raise e
    
    raise Exception("Rate limit exceeded maximum retries")

# --- ENHANCED DETECTION FUNCTIONS ---
def get_audio_features_batch(sp, track_ids):
    """Get audio features for multiple tracks"""
    features = {}
    
    for i in range(0, len(track_ids), 100):
        batch = track_ids[i:i+100]
        try:
            batch_features = safe_sp_call(sp.audio_features, batch)
            for track_id, feature in zip(batch, batch_features):
                if feature:
                    features[track_id] = feature
        except Exception as e:
            print(f"⚠️ Could not fetch audio features for batch: {e}")
    
    return features

def get_artist_info_batch(sp, artist_ids):
    """Get artist information for genre analysis"""
    artist_info = {}
    
    # Remove duplicates while preserving order
    unique_artist_ids = list(dict.fromkeys(artist_ids))
    
    for i in range(0, len(unique_artist_ids), 50):  # Spotify allows 50 artists per request
        batch = unique_artist_ids[i:i+50]
        try:
            batch_artists = safe_sp_call(sp.artists, batch)
            for artist in batch_artists['artists']:
                if artist:
                    artist_info[artist['id']] = artist
        except Exception as e:
            print(f"⚠️ Could not fetch artist info for batch: {e}")
    
    return artist_info

def analyze_audio_features(features):
    """Analyze audio features to determine if track is likely instrumental"""
    if not features:
        return 0, []
    
    score = 0
    reasons = []
    
    # Speechiness analysis (most important for vocals vs instrumental)
    speechiness = features.get('speechiness', 0)
    if speechiness < 0.05:  # Very low speechiness = likely instrumental
        score += 3
        reasons.append(f"Very low speechiness ({speechiness:.3f}) - likely instrumental")
    elif speechiness < 0.1:  # Low speechiness = possibly instrumental
        score += 2
        reasons.append(f"Low speechiness ({speechiness:.3f}) - possibly instrumental")
    elif speechiness > 0.3:  # High speechiness = likely has vocals
        score -= 3
        reasons.append(f"High speechiness ({speechiness:.3f}) - likely has vocals")
    elif speechiness > 0.15:  # Medium speechiness = possibly has vocals
        score -= 1
        reasons.append(f"Medium speechiness ({speechiness:.3f}) - possibly has vocals")
    
    # Instrumentalness analysis
    instrumentalness = features.get('instrumentalness', 0)
    if instrumentalness > 0.7:  # High confidence instrumental
        score += 4
        reasons.append(f"High instrumentalness ({instrumentalness:.3f}) - strong instrumental indicator")
    elif instrumentalness > 0.5:  # Medium confidence instrumental
        score += 2
        reasons.append(f"Medium instrumentalness ({instrumentalness:.3f}) - likely instrumental")
    elif instrumentalness < 0.1:  # Low instrumentalness = likely has vocals
        score -= 1
        reasons.append(f"Low instrumentalness ({instrumentalness:.3f}) - likely has vocals")
    
    # Energy and valence patterns
    energy = features.get('energy', 0)
    valence = features.get('valence', 0)
    
    # Classical/ambient patterns (low energy, variable valence)
    if energy < 0.3:
        score += 0.5
        reasons.append(f"Low energy ({energy:.2f}) - classical/ambient pattern")
    
    # Danceability analysis
    danceability = features.get('danceability', 0)
    if danceability < 0.3 and energy < 0.4:
        score += 1
        reasons.append("Low danceability + energy - classical/meditative pattern")
    
    return score, reasons

def analyze_genres(artist_info_list):
    """Analyze artist genres to determine instrumental likelihood"""
    if not artist_info_list:
        return 0, []
    
    all_genres = []
    for artist_info in artist_info_list:
        if artist_info and 'genres' in artist_info:
            all_genres.extend([genre.lower() for genre in artist_info['genres']])
    
    if not all_genres:
        return 0, ["No genre information available"]
    
    score = 0
    reasons = []
    
    # Check for instrumental genres
    instrumental_matches = [genre for genre in all_genres if any(inst_genre in genre for inst_genre in INSTRUMENTAL_GENRES)]
    if instrumental_matches:
        score += len(instrumental_matches) * 2
        reasons.append(f"Instrumental genres found: {', '.join(instrumental_matches[:3])}...")
    
    # Check for vocal genres
    vocal_matches = [genre for genre in all_genres if any(vocal_genre in genre for vocal_genre in VOCAL_GENRES)]
    if vocal_matches:
        score -= len(vocal_matches)
        reasons.append(f"Vocal genres found: {', '.join(vocal_matches[:3])}...")
    
    return score, reasons

def is_likely_instrumental_advanced(track, audio_features=None, artist_info_list=None):
    """
    Advanced instrumental detection using multiple sophisticated methods
    Returns: (is_instrumental, confidence_score, detailed_reasons)
    """
    track_name = track['name'].lower()
    artist_names = [artist['name'].lower() for artist in track['artists']]
    album_name = track['album']['name'].lower() if track.get('album') else ""
    
    total_score = 0
    all_reasons = []
    
    # 1. Strong keyword analysis
    strong_instrumental_found = any(keyword in track_name for keyword in STRONG_INSTRUMENTAL_KEYWORDS)
    if strong_instrumental_found:
        total_score += 5
        matching_keywords = [kw for kw in STRONG_INSTRUMENTAL_KEYWORDS if kw in track_name]
        all_reasons.append(f"Strong instrumental keywords: {', '.join(matching_keywords[:2])}")
    
    # 2. Medium keyword analysis
    medium_instrumental_found = any(keyword in track_name for keyword in MEDIUM_INSTRUMENTAL_KEYWORDS)
    if medium_instrumental_found:
        total_score += 2
        matching_keywords = [kw for kw in MEDIUM_INSTRUMENTAL_KEYWORDS if kw in track_name]
        all_reasons.append(f"Medium instrumental keywords: {', '.join(matching_keywords[:2])}")
    
    # 3. Strong vocal keyword analysis (negative score)
    strong_vocal_found = any(keyword in track_name for keyword in STRONG_VOCAL_KEYWORDS)
    if strong_vocal_found:
        total_score -= 4
        matching_keywords = [kw for kw in STRONG_VOCAL_KEYWORDS if kw in track_name]
        all_reasons.append(f"Strong vocal keywords: {', '.join(matching_keywords[:2])}")
    
    # 4. Pattern analysis
    for pattern in INSTRUMENTAL_PATTERNS:
        if re.search(pattern, track_name, re.IGNORECASE):
            total_score += 3
            all_reasons.append("Matches instrumental pattern")
            break
    
    for pattern in VOCAL_PATTERNS:
        if re.search(pattern, track_name, re.IGNORECASE):
            total_score -= 3
            all_reasons.append("Matches vocal pattern")
            break
    
    # 5. Album name analysis
    if any(keyword in album_name for keyword in STRONG_INSTRUMENTAL_KEYWORDS):
        total_score += 1
        all_reasons.append("Album name suggests instrumental")
    
    # 6. Artist name analysis
    for artist_name in artist_names:
        if any(artist_type in artist_name for artist_type in INSTRUMENTAL_ARTIST_TYPES):
            total_score += 2
            all_reasons.append(f"Artist type suggests instrumental: {artist_name}")
    
    # 7. Audio features analysis
    if audio_features:
        audio_score, audio_reasons = analyze_audio_features(audio_features)
        total_score += audio_score
        all_reasons.extend(audio_reasons)
    
    # 8. Genre analysis
    if artist_info_list:
        genre_score, genre_reasons = analyze_genres(artist_info_list)
        total_score += genre_score
        all_reasons.extend(genre_reasons)
    
    # 9. Duration analysis
    duration_ms = track.get('duration_ms', 0)
    duration_min = duration_ms / 60000
    
    if duration_min < 0.5:  # Very short tracks (intros/outros)
        total_score += 2
        all_reasons.append(f"Very short duration ({duration_min:.1f}min) - likely intro/outro")
    elif duration_min > 8 and not strong_vocal_found:  # Long tracks without vocal indicators
        total_score += 1
        all_reasons.append(f"Long duration ({duration_min:.1f}min) without vocal indicators")
    
    # 10. Track number analysis (first and last tracks are often instrumental)
    track_number = track.get('track_number', 0)
    if track_number == 1 and 'intro' in track_name:
        total_score += 1
        all_reasons.append("First track with 'intro' in name")
    
    # Decision logic with more nuanced thresholds
    confidence_level = abs(total_score)
    is_instrumental = total_score > 1.5
    
    # Adjust confidence based on how many different methods agreed
    method_count = len([r for r in all_reasons if not r.startswith("No ")])
    if method_count >= 3:
        confidence_level += 0.5
    
    return is_instrumental, total_score, all_reasons

def get_playlist_tracks(sp, playlist_name):
    """Get all tracks from a specific playlist"""
    try:
        playlists = safe_sp_call(sp.current_user_playlists, limit=50)['items']
        playlist_id = None
        
        for playlist in playlists:
            if playlist['name'] == playlist_name:
                playlist_id = playlist['id']
                break
        
        if not playlist_id:
            print(f"❌ Playlist '{playlist_name}' not found!")
            return []
        
        print(f"📋 Found playlist: {playlist_name}")
        
        results = safe_sp_call(sp.playlist_tracks, playlist_id, limit=100)
        all_tracks = results['items']
        
        while results['next']:
            results = safe_sp_call(sp.next, results)
            all_tracks.extend(results['items'])
            print(f"   📥 Fetched {len(all_tracks)} tracks so far...")
        
        valid_tracks = [item['track'] for item in all_tracks if item['track']]
        print(f"🎵 Total tracks in playlist: {len(valid_tracks)}")
        
        return valid_tracks
        
    except Exception as e:
        print(f"❌ Error fetching playlist tracks: {e}")
        return []

def get_or_create_playlist(sp, name, user_id, description=""):
    """Get existing playlist or create new one"""
    try:
        playlists = safe_sp_call(sp.current_user_playlists, limit=50)['items']
        for playlist in playlists:
            if playlist['name'] == name:
                print(f"📝 Found existing playlist: {name}")
                return playlist['id']
        
        print(f"🆕 Creating new playlist: {name}")
        new_playlist = safe_sp_call(sp.user_playlist_create, 
                                   user=user_id, 
                                   name=name, 
                                   description=description)
        return new_playlist['id']
    
    except Exception as e:
        print(f"❌ Error with playlist '{name}': {e}")
        raise e

def clear_playlist(sp, playlist_id):
    """Clear all tracks from a playlist"""
    try:
        tracks = safe_sp_call(sp.playlist_tracks, playlist_id, limit=100)
        all_track_ids = [item['track']['id'] for item in tracks['items'] if item['track']]
        
        while tracks['next']:
            tracks = safe_sp_call(sp.next, tracks)
            all_track_ids.extend([item['track']['id'] for item in tracks['items'] if item['track']])
        
        if all_track_ids:
            print(f"🧹 Clearing {len(all_track_ids)} existing tracks...")
            for i in range(0, len(all_track_ids), 100):
                chunk = all_track_ids[i:i+100]
                safe_sp_call(sp.playlist_remove_all_occurrences_of_items, playlist_id, chunk)
    
    except Exception as e:
        print(f"⚠️ Warning: Could not clear playlist: {e}")

def add_tracks_to_playlist(sp, playlist_id, track_ids, playlist_name):
    """Add tracks to playlist in chunks"""
    if not track_ids:
        print(f"ℹ️ No tracks to add to {playlist_name}")
        return
    
    print(f"➕ Adding {len(track_ids)} tracks to {playlist_name}...")
    
    for i in range(0, len(track_ids), 100):
        chunk = track_ids[i:i+100]
        try:
            safe_sp_call(sp.playlist_add_items, playlist_id, chunk)
            print(f"   📦 Added chunk {i//100 + 1} ({len(chunk)} tracks)")
        except Exception as e:
            print(f"❌ Error adding chunk: {e}")

# --- MAIN FUNCTION ---
def main():
    """Main execution function with enhanced international music detection"""
    
    # Initialize Spotify client
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id='Your Client ID',
            client_secret='Your client secret code',
            redirect_uri='Redirect uri link',
            scope=SCOPE
        ))
        
        user_info = safe_sp_call(sp.current_user)
        user_id = user_info['id']
        print(f"👋 Hello {user_info.get('display_name', user_id)}!")
        
    except Exception as e:
        print(f"❌ Failed to authenticate with Spotify: {e}")
        return

    # Get tracks from source playlist
    print(f"\n🔍 Fetching tracks from '{SOURCE_PLAYLIST_NAME}'...")
    tracks = get_playlist_tracks(sp, SOURCE_PLAYLIST_NAME)
    
    if not tracks:
        print("❌ No tracks found or playlist doesn't exist!")
        return

    # Get audio features for all tracks
    print("\n🎼 Fetching audio features...")
    track_ids = [track['id'] for track in tracks]
    audio_features = get_audio_features_batch(sp, track_ids)
    print(f"✅ Got audio features for {len(audio_features)} tracks")

    # Get artist information for genre analysis
    print("\n👥 Fetching artist information...")
    all_artist_ids = []
    for track in tracks:
        all_artist_ids.extend([artist['id'] for artist in track['artists']])
    
    artist_info = get_artist_info_batch(sp, all_artist_ids)
    print(f"✅ Got artist info for {len(artist_info)} artists")

    # Classify tracks with advanced detection
    print("\n🏷️ Classifying tracks with advanced detection methods...")
    lyrical_tracks = []
    instrumental_tracks = []
    uncertain_tracks = []
    
    for i, track in enumerate(tracks, 1):
        try:
            track_features = audio_features.get(track['id'])
            
            # Get artist info for this track
            track_artist_info = [artist_info.get(artist['id']) for artist in track['artists']]
            
            is_instrumental, confidence, reasons = is_likely_instrumental_advanced(
                track, track_features, track_artist_info
            )
            
            track_info = {
                'id': track['id'],
                'name': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'confidence': confidence,
                'reasons': reasons[:3]  # Keep top 3 reasons for display
            }
            
            if is_instrumental:
                instrumental_tracks.append(track_info)
                if abs(confidence) < 2:  # Low confidence instrumental
                    uncertain_tracks.append(track_info)
            else:
                lyrical_tracks.append(track_info)
                if abs(confidence) < 2:  # Low confidence lyrical
                    uncertain_tracks.append(track_info)
            
            # Progress indicator
            if i % 20 == 0:
                print(f"   🔄 Processed {i}/{len(tracks)} tracks...")
                
        except Exception as e:
            print(f"⚠️ Error classifying track '{track.get('name', 'Unknown')}': {e}")

    # Display detailed results
    print(f"\n📊 Advanced Classification Results:")
    print(f"   🎤 Lyrical tracks: {len(lyrical_tracks)}")
    print(f"   🎵 Instrumental tracks: {len(instrumental_tracks)}")
    print(f"   ❓ Low confidence classifications: {len(uncertain_tracks)}")

    # Show examples of each category
    print(f"\n🎵 Sample Instrumental Classifications:")
    for track in sorted(instrumental_tracks, key=lambda x: x['confidence'], reverse=True)[:3]:
        print(f"   • {track['name']} by {track['artist']}")
        print(f"     Confidence: {track['confidence']:.1f} | Reasons: {', '.join(track['reasons'][:2])}")

    print(f"\n🎤 Sample Lyrical Classifications:")
    for track in sorted([t for t in lyrical_tracks if t['confidence'] < -1], key=lambda x: x['confidence'])[:3]:
        print(f"   • {track['name']} by {track['artist']}")
        print(f"     Confidence: {track['confidence']:.1f} | Reasons: {', '.join(track['reasons'][:2])}")

    if uncertain_tracks:
        print(f"\n🤔 Low Confidence Classifications (please review manually):")
        for track in uncertain_tracks[:5]:
            print(f"   • {track['name']} by {track['artist']} (confidence: {track['confidence']:.1f})")

    # Create playlists
    print(f"\n📝 Setting up playlists...")
    try:
        lyrical_playlist_id = get_or_create_playlist(
            sp, LYRICAL_PLAYLIST_NAME, user_id,
            f"Lyrical songs from {SOURCE_PLAYLIST_NAME} (auto-classified)"
        )
        instrumental_playlist_id = get_or_create_playlist(
            sp, NON_LYRICAL_PLAYLIST_NAME, user_id,
            f"Instrumental songs from {SOURCE_PLAYLIST_NAME} (auto-classified)"
        )
        
        clear_playlists = input("\n🤔 Do you want to clear existing playlists before adding? (y/N): ").lower().startswith('y')
        
        if clear_playlists:
            clear_playlist(sp, lyrical_playlist_id)
            clear_playlist(sp, instrumental_playlist_id)
        
    except Exception as e:
        print(f"❌ Error setting up playlists: {e}")
        return

    # Add tracks to playlists
    print("\n🎯 Adding tracks to playlists...")
    try:
        lyrical_ids = [track['id'] for track in lyrical_tracks]
        instrumental_ids = [track['id'] for track in instrumental_tracks]
        
        add_tracks_to_playlist(sp, lyrical_playlist_id, lyrical_ids, LYRICAL_PLAYLIST_NAME)
        add_tracks_to_playlist(sp, instrumental_playlist_id, instrumental_ids, NON_LYRICAL_PLAYLIST_NAME)
        
        print("\n✅ Advanced separation complete! Check your Spotify playlists:")
        print(f"   🎤 {LYRICAL_PLAYLIST_NAME}: {len(lyrical_tracks)} songs")
        print(f"   🎵 {NON_LYRICAL_PLAYLIST_NAME}: {len(instrumental_tracks)} songs")
        
        if uncertain_tracks:
            print(f"\n💡 Tip: {len(uncertain_tracks)} tracks had low confidence scores.")
            print("   Consider reviewing these manually and moving them if needed.")
        
        # Calculate accuracy estimate
        high_confidence = len([t for t in lyrical_tracks + instrumental_tracks if abs(t['confidence']) > 2])
        total_tracks = len(lyrical_tracks) + len(instrumental_tracks)
        if total_tracks > 0:
            confidence_percentage = (high_confidence / total_tracks) * 100
            print(f"\n📈 Estimated accuracy: {confidence_percentage:.1f}% of classifications are high confidence")
        
    except Exception as e:
        print(f"❌ Error adding tracks to playlists: {e}")

if __name__ == "__main__":

    main()
