import logging
import simplejson as json
from flask import Blueprint, render_template, request, abort, jsonify
from flask_socketio import emit
from app.extensions import socketio
from app.util.rpc import RPC
from app.util.dateutil import format_js_iso
from app.models.MessageModel import Message
from app.models.FeeModel import FeeModel
from app.settings import AppConfig

blueprint = Blueprint('home', __name__, static_folder='../static')

@blueprint.route('/')
def index():
    return render_template('app.html',
                            mt_account=AppConfig.MONKEYTALKS_ACCOUNT,
                            fee=FeeModel.get_fee(),
                            premium=FeeModel.get_premium_fee())

@socketio.on('connect', namespace='/mtchannel')
def on_socket_connect():
    logging.info('SocketIO client connected')

@blueprint.route('/callback', methods=['POST'])
def banano_callback():
    callback_json = request.get_json(silent=True)
    if callback_json is None:
        abort(400, 'failed to parse request json')
    elif 'hash' not in callback_json:
        abort(400, 'invalid request json')
    if 'is_send' in callback_json and callback_json['is_send']:
        rpc = RPC()
        block = rpc.retrieve_block(callback_json['hash'])
        if block is None:
            abort(400, 'block doesn\'t exist')
        else:
            block['hash'] = callback_json['hash']
        # Validate message
        is_valid, message = Message.validate_block(block)
        if not is_valid:
            abort(400, message)
        # Save message to database
        message = Message.save_block_as_message(block)
        if message is None:
            abort(500, 'server error processing message')
        # Emit message to the UI
        emit_message(message)
    return ('',204)

@blueprint.route('/fees', methods=['GET'])
def get_fees():
    return jsonify({'fee':str(FeeModel.get_fee()), 'premium':str(FeeModel.get_premium_fee())})

@blueprint.route('/messages', methods=['GET'])
def get_messages():
    """Load initial messages"""
    message_response = []
    for m in Message.select().where(Message.hidden == False).order_by(Message.id.desc()).limit(100):
        message_response.append(format_message(m))
    return jsonify(message_response)

def format_message(message : Message) -> dict:
    message_json = {
        'id': message.id,
        'content': message.message_in_raw,
        'date': format_js_iso(message.created_at),
        'premium': message.premium,
        'address': message.address,
        'count': Message.get_message_count(message.address)
    }
    return message_json

def emit_message(message : Message):
    """Emit a new chat message to the UI - Broadcasted to all clients"""
    emit('new_message', json.dumps(format_message(message)), namespace='/mtchannel', broadcast=True)
