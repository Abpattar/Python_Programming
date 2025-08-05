import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException

# --- CONFIGURATION ---
SCOPE = "user-library-read playlist-modify-public playlist-modify-private"
INDIAN_PLAYLIST_NAME = "🌏 Indian Songs"
INTERNATIONAL_PLAYLIST_NAME = "🌍 International Songs"

# Add more for more precise sorting
# --- KEYWORDS ---
INDIAN_LANG_KEYWORDS = [
    'hindi', 'kannada', 'telugu', 'tamil', 'malayalam', 'bengali', 'assamese', 'sanskrit',
    'punjabi', 'gujarati', 'marathi', 'odia', 'bhojpuri', 'urdu'
]

# Add more for more precise sorting
INDIAN_GENRE_KEYWORDS = [
    'sandalwood', 'bollywood', 'tollywood', 'kollywood', 'mollywood', 'devotional',
    'bhajan', 'qawwali', 'classical indian', 'carnatic', 'hindustani', 'raga',
    'ghazal', 'kirtan', 'mantra', 'fusion indian', 'indipop', 'filmi', 'sufi',
    'indian classical', 'indian folk', 'indian pop'
]
# --- Add more for more precise sorting ---
POPULAR_INDIAN_ARTISTS = [
    'a.r. rahman', 'ilaiyaraaja', 'shankar mahadevan', 'udit narayan',
    'lata mangeshkar', 'kishore kumar', 'anirudh ravichander', 'yuvan shankar raja',
    'harris jayaraj', 'vishal-shekhar', 'shankar-ehsaan-loy', 'amit trivedi',
    'arijit singh', 'shreya ghoshal', 'k.j. yesudas', 's.p. balasubrahmanyam',
    'devi sri prasad', 'thaman s', 'ghibran', 'santhosh narayanan',
    'ravi basrur', 'ajaneesh loknath', 'b. ajaneesh loknath', 'vijay prakash', 
    'sonu nigam', 'm.m keeravaani', 'v. harikrishna', 'anup bhandari',
    'rajesh krishnan', 'ananya bhat', 'kala bhairava', 'ankit tiwari', 'raghu dixit',
    'dr. rajkumar', 'rajkumar', 'rahat fateh ali khan', 'nusrat fateh ali khan',
    'mohammed rafi', 'mukesh', 'hemant kumar', 'manna dey', 'jagjit singh',
    'ghulam ali', 'hariharan', 'unni menon', 'kailash kher', 'sukhwinder singh'
]
# Add more for more precise sorting
# Additional keywords for better detection
INDIAN_SONG_KEYWORDS = [
    'bollywood', 'item number', 'playback', 'duet', 'sad version', 'unplugged',
    'qawwali', 'thumri', 'bhajan', 'aarti', 'shloka'
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
            if e.http_status == 429:  # Rate limit exceeded
                retry_after = int(e.headers.get("Retry-After", 5))
                print(f"⚠️ Rate limit hit. Waiting for {retry_after} seconds... (Attempt {retry_count + 1}/{max_retries})")
                time.sleep(retry_after + 1)
                retry_count += 1
            elif e.http_status == 401:  # Unauthorized
                print("❌ Authentication failed. Please check your credentials.")
                raise e
            else:
                print(f"❌ Spotify API error: {e}")
                raise e
    
    print("❌ Max retries exceeded. Please try again later.")
    raise Exception("Rate limit exceeded maximum retries")

# --- ENHANCED DETECTION FUNCTIONS ---
def is_indian_track(track, sp):
    """Enhanced Indian track detection with multiple criteria"""
    
    # Check artist names
    artist_names = [artist['name'].lower() for artist in track['artists']]
    artist_match = any(any(indian_artist in name for indian_artist in POPULAR_INDIAN_ARTISTS) for name in artist_names)
    
    # Check track name for language keywords
    track_name = track['name'].lower()
    lang_match = any(lang in track_name for lang in INDIAN_LANG_KEYWORDS)
    
    # Check track name for Indian song keywords
    song_keyword_match = any(keyword in track_name for keyword in INDIAN_SONG_KEYWORDS)
    
    # Check genres (with error handling)
    genre_match = False
    try:
        artist_id = track['artists'][0]['id']
        artist = safe_sp_call(sp.artist, artist_id)
        genres = [genre.lower() for genre in artist.get('genres', [])]
        genre_match = any(any(indian_genre in genre for indian_genre in INDIAN_GENRE_KEYWORDS) for genre in genres)
    except Exception as e:
        print(f"⚠️ Could not fetch genre for artist: {e}")
    
    # Check album name for Indian keywords
    album_match = False
    if 'album' in track and track['album']:
        album_name = track['album']['name'].lower()
        album_match = any(keyword in album_name for keyword in INDIAN_LANG_KEYWORDS + INDIAN_SONG_KEYWORDS)
    
    # Return True if any criteria matches
    is_indian = artist_match or lang_match or genre_match or song_keyword_match or album_match
    
    # Debug output for uncertain cases
    if not is_indian and any(keyword in track_name for keyword in ['india', 'desi', 'bollywood']):
        print(f"🤔 Uncertain classification: {track['name']} by {', '.join([a['name'] for a in track['artists']])}")
    
    return is_indian

def get_or_create_playlist(sp, name, user_id, description=""):
    """Get existing playlist or create new one"""
    try:
        # Check existing playlists
        playlists = safe_sp_call(sp.current_user_playlists, limit=50)['items']
        for playlist in playlists:
            if playlist['name'] == name:
                print(f"📝 Found existing playlist: {name}")
                return playlist['id']
        
        # Create new playlist if not found
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
        # Get current tracks
        tracks = safe_sp_call(sp.playlist_tracks, playlist_id, limit=100)
        all_track_ids = [item['track']['id'] for item in tracks['items'] if item['track']]
        
        # Handle pagination
        while tracks['next']:
            tracks = safe_sp_call(sp.next, tracks)
            all_track_ids.extend([item['track']['id'] for item in tracks['items'] if item['track']])
        
        # Remove tracks in chunks
        if all_track_ids:
            print(f"🧹 Clearing {len(all_track_ids)} existing tracks...")
            for chunk in chunkify(all_track_ids, 100):
                safe_sp_call(sp.playlist_remove_all_occurrences_of_items, playlist_id, chunk)
    
    except Exception as e:
        print(f"⚠️ Warning: Could not clear playlist: {e}")

def chunkify(lst, size):
    """Split list into chunks of specified size"""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def add_tracks_to_playlist(sp, playlist_id, track_ids, playlist_name):
    """Add tracks to playlist in chunks with progress tracking"""
    if not track_ids:
        print(f"ℹ️ No tracks to add to {playlist_name}")
        return
    
    print(f"➕ Adding {len(track_ids)} tracks to {playlist_name}...")
    
    chunk_count = 0
    total_chunks = (len(track_ids) + 99) // 100  # Ceiling division
    
    for chunk in chunkify(track_ids, 100):
        chunk_count += 1
        try:
            safe_sp_call(sp.playlist_add_items, playlist_id, chunk)
            print(f"   📦 Added chunk {chunk_count}/{total_chunks} ({len(chunk)} tracks)")
        except Exception as e:
            print(f"❌ Error adding chunk {chunk_count}: {e}")

# --- MAIN FUNCTION ---
def main():
    """Main execution function"""
    
    # Initialize Spotify client
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id='Your client ID',
            client_secret='Your client secret code',
            redirect_uri='Your redirect uri',
            scope=SCOPE
        ))
        
        # Test authentication
        user_info = safe_sp_call(sp.current_user)
        user_id = user_info['id']
        print(f"👋 Hello {user_info.get('display_name', user_id)}!")
        
    except Exception as e:
        print(f"❌ Failed to authenticate with Spotify: {e}")
        return

    # Fetch all liked songs
    print("\n🔍 Fetching your liked songs...")
    try:
        results = safe_sp_call(sp.current_user_saved_tracks, limit=50)
        all_tracks = results['items']
        
        # Handle pagination
        while results['next']:
            results = safe_sp_call(sp.next, results)
            all_tracks.extend(results['items'])
            print(f"   📥 Fetched {len(all_tracks)} songs so far...")
        
        print(f"🎵 Total liked songs found: {len(all_tracks)}")
        
    except Exception as e:
        print(f"❌ Error fetching liked songs: {e}")
        return

    # Classify tracks
    print("\n🏷️ Classifying tracks as Indian or International...")
    indian_tracks = []
    international_tracks = []
    
    for i, item in enumerate(all_tracks, 1):
        track = item['track']
        if not track:  # Skip if track is None (deleted tracks)
            continue
            
        try:
            if is_indian_track(track, sp):
                indian_tracks.append(track['id'])
            else:
                international_tracks.append(track['id'])
                
            # Progress indicator
            if i % 50 == 0:
                print(f"   🔄 Processed {i}/{len(all_tracks)} tracks...")
                
        except Exception as e:
            print(f"⚠️ Error classifying track '{track.get('name', 'Unknown')}': {e}")

    print(f"\n📊 Classification Results:")
    print(f"   🇮🇳 Indian tracks: {len(indian_tracks)}")
    print(f"   🌍 International tracks: {len(international_tracks)}")

    # Create/get playlists
    print("\n📝 Setting up playlists...")
    try:
        indian_playlist_id = get_or_create_playlist(
            sp, INDIAN_PLAYLIST_NAME, user_id, 
            "Auto-generated playlist containing Indian songs from your liked music"
        )
        international_playlist_id = get_or_create_playlist(
            sp, INTERNATIONAL_PLAYLIST_NAME, user_id,
            "Auto-generated playlist containing International songs from your liked music"
        )
        
        # Ask user if they want to clear existing playlists
        clear_playlists = input("\n🤔 Do you want to clear existing playlists before adding? (y/N): ").lower().startswith('y')
        
        if clear_playlists:
            clear_playlist(sp, indian_playlist_id)
            clear_playlist(sp, international_playlist_id)
        
    except Exception as e:
        print(f"❌ Error setting up playlists: {e}")
        return

    # Add tracks to playlists
    print("\n🎯 Adding tracks to playlists...")
    try:
        add_tracks_to_playlist(sp, indian_playlist_id, indian_tracks, INDIAN_PLAYLIST_NAME)
        add_tracks_to_playlist(sp, international_playlist_id, international_tracks, INTERNATIONAL_PLAYLIST_NAME)
        
        print("\n✅ Sorting complete! Check your Spotify playlists:")
        print(f"   🇮🇳 {INDIAN_PLAYLIST_NAME}: {len(indian_tracks)} songs")
        print(f"   🌍 {INTERNATIONAL_PLAYLIST_NAME}: {len(international_tracks)} songs")
        
    except Exception as e:
        print(f"❌ Error adding tracks to playlists: {e}")

if __name__ == "__main__":

    main()
