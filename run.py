from flask import *
from flask_socketio import *
import shutil
import os
import json
import zipfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import random
import string

app = Flask(__name__)
socketio = SocketIO(app)
clients = {}
@app.route('/')
def index():
    return render_template('index.html')
def load_config():
    with open('config.json', 'r') as config_file:
        return json.load(config_file)
def get_default_data():
    with open('templates/guest/data.json', 'r') as default_data_file:
        return json.load(default_data_file)
def get_usernames():
    usernames = []
    for client_id in clients.keys():
        user_data = get_data(client_id)
        usernames.append(user_data['username'])
    return usernames
def get_data(id):
    with open(f'Players/{id}/data.json', 'r') as data_file:
        return json.load(data_file)
def save_data(id, data):
    with open(f'Players/{id}/data.json', 'w') as data_file:
        json.dump(data, data_file)







@app.route('/request_change_email', methods=['POST'])
def request_change_email():
    data = request.json
    client_id = data['client_id']
    new_email = data['new_email']

    user_data = get_data(client_id)
    defaults = get_default_data()

    if user_data['email'] == defaults['email']:
        user_data['email'] = new_email
        save_data(client_id, user_data)
        return jsonify({"message": "Email set successfully"}), 200
    else:
        # Generate a confirmation code
        confirmation_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        # Store the confirmation code and new email in the temporary dictionary
        confirmation_data[client_id] = {'confirmation_code': confirmation_code, 'new_email': new_email}

        # Simulate sending the confirmation code by printing it
        print(f"Confirmation code for {client_id}: {confirmation_code}")

        return jsonify({"message": "Confirmation code sent"}), 200
confirmation_data = {}
@app.route('/confirm_change_email', methods=['POST'])
def confirm_change_email():
    data = request.json
    client_id = data['client_id']
    confirmation_code = data['confirmation_code']

    if client_id in confirmation_data and confirmation_data[client_id]['confirmation_code'] == confirmation_code:
        user_data = get_data(client_id)
        user_data['email'] = confirmation_data[client_id]['new_email']
        save_data(client_id, user_data)
        del confirmation_data[client_id]
        return jsonify({"message": "Email changed successfully"}), 200
    else:
        return jsonify({"message": "Invalid confirmation code"}), 400
@app.route('/change_username', methods=['POST'])
def change_username():
    data = request.json
    client_id = data['client_id']
    new_username = data['new_username']

    user_data = get_data(client_id)
    defaults = get_default_data()

    if user_data['username'] == defaults['username']:
        # Allow change for free
        user_data['username'] = new_username
        save_data(client_id, user_data)
        emit('update_clients', {'clients': get_usernames()}, broadcast=True)
        return jsonify({"message": "Username changed successfully", "new_username": new_username}), 200
    else:
        # Check if the user has enough money
        if user_data['money'] >= 1:
            user_data['money'] -= 1
            user_data['username'] = new_username
            save_data(client_id, user_data)
            emit('update_clients', {'clients': get_usernames()}, broadcast=True)
            return jsonify({"message": "Username changed successfully", "new_username": new_username, "remaining_money": user_data['money']}), 200
        else:
            return jsonify({"message": "Not enough money"}), 400
def export_save(id):
    config = load_config()
    from_email = config['from_email']
    from_password = config['from_password']
    player_data = get_data(id)
    to_email = player_data['email']
    save_dir = f'Players/{id}'
    zip_path = f'tmp/{id}.zip'

    try:
        # Zip the save directory
        shutil.make_archive(zip_path.replace('.zip', ''), 'zip', save_dir)

        # Create message container
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = "RexServer -> SAVEFILE <- Thank you for playing!"

        body = "This is an alpha email placeholder..."
        msg.attach(MIMEText(body, 'plain'))

        # Attach the zip file
        if os.path.exists(zip_path):
            with open(zip_path, 'rb') as attachment_file:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(attachment_file.read())
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename={os.path.basename(zip_path)}')
            msg.attach(attachment)
        else:
            print(f"Failed to export save for: {id}")
            return

        # Create SMTP session for sending the mail
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()  # Enable security
            server.login(from_email, from_password)  # Login with the provided credentials
            text = msg.as_string()
            server.sendmail(from_email, to_email, text)
            print(f'Email sent to {to_email}')

        # Cleanup the zip file after sending
        os.remove(zip_path)
        print(f'Save exported to: {id}')

    except Exception as e:
        print(f"An error occurred while exporting save: {e}")
@app.route('/upload_save', methods=['POST'])
def upload_save():
    client_id = request.form.get('client_id')  # Retrieve client_id from form data
    if 'file' not in request.files:
        print(f"Failed while uploading save for {client_id}")
        return jsonify({"message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        print(f"Failed while uploading save for {client_id}")
        return jsonify({"message": "No selected file"}), 400
    if file:
        save_path = os.path.join('tmp', f"{client_id}.zip")
        file.save(save_path)

        # Extract the zip file
        temp_extract_path = os.path.join('tmp', client_id)
        with zipfile.ZipFile(save_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_path)

        current_path = temp_extract_path

        # Traverse directories to find the one containing data.json
        while True:
            items = os.listdir(current_path)
            if 'data.json' in items:
                break
            elif len(items) == 1 and os.path.isdir(os.path.join(current_path, items[0])):
                current_path = os.path.join(current_path, items[0])
            else:
                print(f"No valid save directory found for {client_id}")
                return jsonify({"message": "Invalid save file structure"}), 400

        final_path = os.path.join('Players', client_id)

        # Remove any existing directory with the same name
        if os.path.exists(final_path):
            shutil.rmtree(final_path)

        # Move the valid directory to the Players directory, renaming it to the client ID
        shutil.move(current_path, final_path)

        # Remove the temporary extraction directory and the zip file
        if os.path.exists(temp_extract_path):
            shutil.rmtree(temp_extract_path)
        if os.path.exists(save_path):
            os.remove(save_path)

        socketio.emit('update_clients', {'clients': get_usernames()})
        print(f"Save uploaded by {client_id}")
        return jsonify({"message": "Save uploaded successfully"}), 200

@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    clients[client_id] = {'connected': True}
    print(f"Client connected: {client_id}")
    emit('assign_id', {'client_id': client_id}, to=client_id)


    # Define the source and destination paths
    user_template = os.path.join('templates', 'guest')
    players = os.path.join('Players', client_id)
    # Copy the folder and its contents
    shutil.copytree(user_template, players)
    print(f"New save created for {client_id}")
    emit('update_clients', {'clients': get_usernames()}, broadcast=True)
@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    if client_id:
        clients.pop(client_id)
        print(f"Client disconnected: {client_id}")
        emit('update_clients', {'clients': get_usernames()}, broadcast=True)

        export_save(client_id)
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)