import logging
import sys
import boto3
import openai
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# Configure logging to write to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# Create a custom logger
logger = logging.getLogger(__name__)
# Create handlers
c_handler = logging.StreamHandler()
f_handler = logging.FileHandler('/var/log/flask/error.log')
# Create formatters and add them to handlers
c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(c_format)
f_handler.setFormatter(f_format)
# Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)

# Set the upload folder in the config
app.config['UPLOAD_FOLDER'] = '/tmp/uploads/images'  # Use /tmp for temporary storage
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) # Ensure the upload directory exists

# AWS S3 Configuration
AWS_S3_BUCKET = 'glucose-tracker-images'
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name='eu-north-1'
)

# OpenAI Configuration
openai.api_key = os.environ.get('OPENAI_API_KEY')
MODEL = 'gpt-4-vision-preview'

# Health Check Route
@app.route('/health')
def health_check():
    app.logger.info('Health check accessed')
    return 'Healthy', 200

# This is to define the type of files that the Python app allows
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'heic'}

# This is the app.route to get the image from the iOS app
@app.route('/upload_image', methods=['POST'])
def upload_image():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image part in the request"}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed"}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Upload to S3
        s3_client.upload_file(
            Filename=filepath,
            Bucket=AWS_S3_BUCKET,
            Key=filename
        )
        image_url = f'https://{AWS_S3_BUCKET}.s3.eu-north-1.amazonaws.com/{filename}'

        # Prepare the OpenAI request
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "your response should be a table format with the identified food items in the image. analyze the image and for each identified food provide general nutritional content, provide estimated values based on image-based estimated grams and servings sizes. Show: its grams, its GI, its GL, its carbohydrate content (in grams), its fat content (in grams), its protein content (in grams) and its calories. then, give the total answer for the whole meal in terms of total grams (based on estimate from image), total GL, total carbohydrate content (in grams), total fat content (in grams), total protein content (in grams) and total calories. provide numerical responses."},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ]

        # Send the request to OpenAI
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            max_tokens=550
        )

        # Clean up: Delete the local file after uploading
        os.remove(filepath)

        # Extract the response
        message_content = response.choices[0].message.content

        # Construct a JSON response
        return jsonify({
            "status": "success",
            "message": "Image processed successfully",
            "analysis_result": message_content
        })
    except Exception as e:
        # Log the error before sending a response
        app.logger.error(f'An error occurred: {str(e)}')
        return jsonify({
            "status": "error",
            "message": "An error occurred while processing the image"
        }), 500

# Error handling example
@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error before sending a response
    app.logger.error(f'An error occurred: {str(e)}')
    return jsonify({"status": "error", "message": "An internal server error occurred"}), 500

if __name__ == '__main__':
    pass

