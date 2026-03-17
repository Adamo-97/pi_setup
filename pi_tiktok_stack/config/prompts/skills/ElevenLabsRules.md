# Arabic Text to Speech Best Practices Guide
## Using ElevenLabs API with Professional Voice Clone

---

## Table of Contents
1. [API Request Format](#api-request-format)
2. [Recommended Model for Arabic PVC](#recommended-model-for-arabic-pvc)
3. [Voice Settings Explained](#voice-settings-explained)
4. [Character Limitations](#character-limitations)
5. [Arabic-Specific Best Practices](#arabic-specific-best-practices)
6. [Prompting for Emotion & Delivery](#prompting-for-emotion--delivery)
7. [Pauses & Timing](#pauses--timing)
8. [Audio Output Formats](#audio-output-formats)
9. [Regional Arabic Accents](#regional-arabic-accents)
10. [Language Override](#language-override)
11. [Pronunciation Dictionaries](#pronunciation-dictionaries)
12. [Streaming vs Non-Streaming](#streaming-vs-non-streaming)
13. [Rate Limiting](#rate-limiting)
14. [Error Handling](#error-handling)
15. [Complete Code Examples](#complete-code-examples)
16. [Testing Recommendations](#testing-recommendations)
17. [Common Issues & Solutions](#common-issues--solutions)
18. [Additional Resources](#additional-resources)

---

## API Request Format

**Endpoint:** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`

**Required Headers:**
- `xi-api-key`: Your API key
- `Content-Type`: application/json

**Request Body (JSON):**
```json
{
  "text": "Your Arabic text here",
  "model_id": "eleven_multilingual_v2",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": true
  }
}
```

## Recommended Model for Arabic PVC

**Best Choice:** `eleven_multilingual_v2` or `eleven_turbo_v2_5`

- **Multilingual v2:** Highest quality, emotionally nuanced
- **Turbo v2.5:** Faster with good quality
- **Avoid v3 for now** - Professional Voice Clones aren't fully optimized for v3 yet

## Voice Settings Explained

### Non-v3 Models

**Stability** (zero point zero to one point zero, default zero point five):

- Lower values (zero point three to zero point four): More expressive but less consistent
- Higher values (zero point six to zero point eight): More consistent but less expressive
- For Arabic narration: Start with zero point five to zero point six

**Similarity Boost** (zero point zero to one point zero, default zero point seventy-five):

- Controls how closely output matches your original voice
- Keep at zero point seventy-five to zero point eighty-five for best clone accuracy

**Style Exaggeration** (zero point zero to one point zero, default zero point zero):

- Amplifies the voice's natural style
- Use sparingly (zero point one to zero point three) for Arabic content
- Model-dependent feature

**Speaker Boost** (boolean, default true):

- Enhances similarity at higher computational cost
- Keep enabled for Professional Voice Clones

## Character Limitations

**Per Request:**

- Maximum: five thousand characters per API call
- For longer content, split into chunks
- Recommended chunk size: one thousand to two thousand characters for optimal quality

**Monthly Quota:**

- Your Creator plan: one hundred ten thousand characters remaining
- Resets on: April eighth, twenty twenty-six

## Arabic-Specific Best Practices

### 1. Text Formatting

- Use proper Arabic diacritics (tashkeel) for accurate pronunciation
- Include punctuation for natural pauses
- Use exclamation marks and question marks to convey emotion

### 2. Handling Mixed Language (Arabic + English)

Default behavior: English words in Arabic text will be pronounced with an English accent

**Workarounds:**

- Spell out English words phonetically in Arabic script for Arabic pronunciation
  - Example: Instead of "Radio", write "راديو"
- Numbers: Write numbers as Arabic words, not digits
  - Instead of "eleven", write "أحد عشر"
  - Instead of "twenty twenty-six", write "ألفان وستة وعشرون"

### 3. Known Limitations

- Numbers in digit form may default to English pronunciation
- Acronyms may be read in English
- Foreign brand names might not sound natural
- **Solution:** Spell everything out in Arabic text

## Prompting for Emotion & Delivery

The model interprets emotional context from your text:

**Add descriptive text:**

- "قال بحماس" (he said excitedly)
- "همست بهدوء" (she whispered quietly)
- "صرخ بغضب" (he shouted angrily)

**Use punctuation:**

- Exclamation marks for excitement: "!رائع"
- Ellipsis for pauses: "انتظر... دعني أفكر"
- Question marks for inquiry: "هل تفهم؟"

## Pauses & Timing

For natural pauses (up to three seconds):

- Use commas for short pauses
- Use periods for medium pauses
- Use multiple periods or line breaks for longer pauses

**Note:** Don't overuse - excessive pauses can cause instability

## Audio Output Formats

**Available formats:**

- **MP3** (default): twenty-two point zero-five kHz to forty-four point one kHz
- **PCM:** sixteen kHz to forty-four point one kHz, sixteen-bit depth
- **mu-law:** eight kHz (telephony)
- **Opus:** forty-eight kHz

**Recommended for Arabic content:**

- MP3 at forty-four point one kHz, one hundred twenty-eight kbps for high quality
- Opus for streaming applications

**Specify in request:**

```json
{
  "output_format": "mp3_44100_128"
}
```

## Regional Arabic Accents

ElevenLabs TTS can adapt to various regional Arabic accents. Your Professional Voice Clone will maintain the accent from your training samples.

**Supported regional variations:**

- Saudi Arabian Arabic
- UAE Arabic
- Egyptian Arabic
- Levantine Arabic
- Maghrebi Arabic

## Language Override

Force Arabic language detection:

If the model incorrectly detects the language, you can override it:

```json
{
  "text": "Your Arabic text here",
  "model_id": "eleven_multilingual_v2",
  "language_code": "ar"
}
```

**Supported Arabic language codes:**

- `ar` - Standard Arabic
- Regional codes may be available depending on the model

## Pronunciation Dictionaries

For specialized terminology or consistent pronunciation:

You can create pronunciation dictionaries to ensure specific words are pronounced correctly every time.

**Use cases:**

- Brand names
- Technical terms
- Names of people or places
- Acronyms

**How to use:**

1. Navigate to your voice settings in the ElevenLabs dashboard
2. Add pronunciation rules
3. The dictionary will apply automatically to all API calls using that voice

## Streaming vs Non-Streaming

### Non-Streaming (Default)

**Endpoint:** `POST /v1/text-to-speech/{voice_id}`

- Returns complete audio file
- Simpler to implement
- Higher latency (wait for full generation)

### Streaming

**Endpoint:** `POST /v1/text-to-speech/{voice_id}/stream`

- Returns audio chunks as they're generated
- Lower perceived latency
- Better for real-time applications

**Example streaming request:**

```json
{
  "text": "Your Arabic text here",
  "model_id": "eleven_multilingual_v2",
  "stream": true
}
```

## Rate Limiting

**Creator Plan Limits:**

- Concurrent requests: Limited based on your tier
- Characters per month: one hundred ten thousand
- Request rate: Subject to API rate limits

**Best practices:**

- Implement exponential backoff for retries
- Monitor your quota usage
- Cache generated audio when possible
- Split large texts into smaller chunks

**Rate limit headers in response:**

- `X-RateLimit-Limit` - Your rate limit
- `X-RateLimit-Remaining` - Remaining requests
- `X-RateLimit-Reset` - When the limit resets

## Error Handling

### Common HTTP Status Codes

**four hundred (Bad Request):**

- Invalid parameters
- Text exceeds character limit
- Invalid voice ID

**four hundred one (Unauthorized):**

- Invalid or missing API key
- Check your `xi-api-key` header

**four hundred two (Payment Required):**

- Insufficient credits
- Quota exceeded

**four hundred twenty-two (Unprocessable Entity):**

- Invalid voice settings
- Unsupported language for the model

**four hundred twenty-nine (Too Many Requests):**

- Rate limit exceeded
- Implement exponential backoff

**five hundred (Internal Server Error):**

- Server-side issue
- Retry with exponential backoff

### Error Response Format

```json
{
  "detail": {
    "status": "error_code",
    "message": "Human-readable error message"
  }
}
```

### Recommended Error Handling Pattern

```python
import time
import requests

def generate_speech_with_retry(text, voice_id, api_key, max_retries=3):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "use_speaker_boost": True
        }
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                return response.content
            elif response.status_code == 429:
                # Rate limited - wait and retry
                wait_time = (2 ** attempt) * 1  # Exponential backoff
                print(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            elif response.status_code == 401:
                raise Exception("Invalid API key")
            elif response.status_code == 402:
                raise Exception("Insufficient credits")
            else:
                print(f"Error {response.status_code}: {response.text}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise Exception(f"Failed after {max_retries} attempts")
        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    raise Exception("Max retries exceeded")
```

## Complete Code Examples

### Python Example (Non-Streaming)

```python
import requests
import os

# Configuration
VOICE_ID = "your_voice_id_here"  # Replace with your copied voice ID
API_KEY = os.getenv("ELEVENLABS_API_KEY")  # Store in environment variable

# API endpoint
url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

# Headers
headers = {
    "xi-api-key": API_KEY,
    "Content-Type": "application/json"
}

# Request body
data = {
    "text": "مرحباً بك في عالم الذكاء الاصطناعي. هذا مثال على نص عربي يحتوي على كلمات إنجليزية مثل راديو وتلفزيون.",
    "model_id": "eleven_multilingual_v2",
    "voice_settings": {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True
    },
    "language_code": "ar"  # Force Arabic detection
}

# Make request
response = requests.post(url, json=data, headers=headers)

# Save audio file
if response.status_code == 200:
    with open("output_arabic.mp3", "wb") as f:
        f.write(response.content)
    print("Audio generated successfully!")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
```

### Python Example (Streaming)

```python
import requests
import os

VOICE_ID = "your_voice_id_here"
API_KEY = os.getenv("ELEVENLABS_API_KEY")

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"

headers = {
    "xi-api-key": API_KEY,
    "Content-Type": "application/json"
}

data = {
    "text": "مرحباً بك في عالم الذكاء الاصطناعي.",
    "model_id": "eleven_multilingual_v2",
    "voice_settings": {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "use_speaker_boost": True
    }
}

# Stream the response
response = requests.post(url, json=data, headers=headers, stream=True)

if response.status_code == 200:
    with open("output_arabic_stream.mp3", "wb") as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    print("Streaming audio generated successfully!")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
```

### JavaScript Example (Node.js)

```javascript
const fs = require('fs');
const axios = require('axios');

const VOICE_ID = 'your_voice_id_here';
const API_KEY = process.env.ELEVENLABS_API_KEY;

const url = `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}`;

const headers = {
  'xi-api-key': API_KEY,
  'Content-Type': 'application/json'
};

const data = {
  text: 'مرحباً بك في عالم الذكاء الاصطناعي. هذا مثال على نص عربي.',
  model_id: 'eleven_multilingual_v2',
  voice_settings: {
    stability: 0.5,
    similarity_boost: 0.75,
    style: 0.0,
    use_speaker_boost: true
  },
  language_code: 'ar'
};

axios.post(url, data, {
  headers: headers,
  responseType: 'arraybuffer'
})
  .then(response => {
    fs.writeFileSync('output_arabic.mp3', response.data);
    console.log('Audio generated successfully!');
  })
  .catch(error => {
    console.error('Error:', error.response ? error.response.status : error.message);
    if (error.response) {
      console.error(error.response.data.toString());
    }
  });
```

### JavaScript Example (Streaming with Web Audio API)

```javascript
const VOICE_ID = 'your_voice_id_here';
const API_KEY = 'your_api_key_here';

async function streamArabicTTS(text) {
  const url = `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}/stream`;
  
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'xi-api-key': API_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      text: text,
      model_id: 'eleven_multilingual_v2',
      voice_settings: {
        stability: 0.5,
        similarity_boost: 0.75,
        use_speaker_boost: true
      }
    })
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body.getReader();
  const chunks = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }

  // Combine chunks into a single Blob
  const audioBlob = new Blob(chunks, { type: 'audio/mpeg' });
  const audioUrl = URL.createObjectURL(audioBlob);
  
  // Play the audio
  const audio = new Audio(audioUrl);
  audio.play();
}

// Usage
streamArabicTTS('مرحباً بك في عالم الذكاء الاصطناعي');
```

## Testing Recommendations

### 1. Start Simple

- Test with short Arabic phrases first
- Verify pronunciation accuracy
- Adjust voice settings based on results

**Test phrases:**

- "مرحباً، كيف حالك؟"
- "هذا اختبار للصوت المستنسخ"
- "أحد عشر، اثنا عشر، ثلاثة عشر"

### 2. Test Mixed Content

- Try Arabic text with English words
- Determine if phonetic spelling is needed
- Test numbers and dates

**Test phrases:**

- "استمع إلى الراديو كل يوم"
- "في عام ألفان وستة وعشرون"
- "شركة مايكروسوفت وشركة جوجل"

### 3. Iterate on Settings

- Adjust stability for your use case
- Test different style values
- Compare Multilingual v2 vs Turbo v2.5

**Recommended test matrix:**

| Stability | Similarity | Style | Use Case |
|-----------|-----------|-------|----------|
| 0.4 | 0.75 | 0.0 | Expressive narration |
| 0.5 | 0.75 | 0.0 | Balanced (default) |
| 0.6 | 0.80 | 0.0 | Consistent audiobook |
| 0.5 | 0.85 | 0.2 | High similarity + style |

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| English words sound wrong | Spell phonetically in Arabic |
| Numbers read in English | Write as Arabic words |
| Voice sounds robotic | Lower stability to zero point four |
| Voice is inconsistent | Raise stability to zero point six |
| Doesn't match clone | Increase similarity boost to zero point eighty-five |
| Lacks emotion | Add descriptive text and punctuation |
| Rate limit errors | Implement exponential backoff |
| Quota exceeded | Monitor usage, upgrade plan if needed |
| Wrong language detected | Use language_code: "ar" parameter |
| Pronunciation errors | Use pronunciation dictionaries |
| High latency | Use streaming endpoint |
| Audio quality issues | Increase output format quality |

## Additional Resources

- **Full API Documentation:** elevenlabs.io/docs
- **Arabic language support** in Multilingual v2
- **Professional Voice Clone** optimization updates
- **API Reference:** elevenlabs.io/docs/api-reference
- **Community Forum:** For questions and discussions
- **Support:** Available for all tiers including Creator

## Quick Reference Card

### Essential Parameters

```json
{
  "text": "Your Arabic text",
  "model_id": "eleven_multilingual_v2",
  "language_code": "ar",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "use_speaker_boost": true
  }
}
```

### Your Account Details

- **Plan:** Creator
- **Monthly Credits:** one hundred ten thousand characters
- **Next Reset:** April eighth, twenty twenty-six
- **Professional Voice Clones:** one slot (currently in training)

## Notes

- Your Professional Voice Clone is currently in training and will be ready within two to six hours
- Once ready, you can start testing with these best practices
- Remember to store your API key securely in environment variables
- Never commit API keys to version control
- Monitor your credit usage to avoid unexpected quota exhaustion

---

**Document Version:** one point zero
**Last Updated:** March eighth, twenty twenty-six
**Created for:** Arabic Text to Speech with Professional Voice Clone
