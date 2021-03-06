#! /usr/bin/env python
"""Run a YOLO_v2 style detection model on test images."""
import argparse
import colorsys
import imghdr
import os
import random
import sys
import numpy as np
from keras import backend as K
from keras.models import load_model
from PIL import Image, ImageDraw, ImageFont
from yad2k.models.keras_yolo import yolo_eval, yolo_head
import cv2
file_name = sys.argv[1]
model_path = 'YAD2K/model_data/yolo.h5'
anchors_path = 'YAD2K/model_data/yolo_anchors.txt'
classes_path = 'YAD2K/model_data/coco_classes.txt'
test_path = '.'
output_path = file_name.rsplit('.', 1)[0]  + "_yolo." +  file_name.rsplit('.', 1)[1]
score_threshold = 0.3
iou_threshold = 0.5


sess = K.get_session()

with open(classes_path) as f:
    class_names = f.readlines()
class_names = [c.strip() for c in class_names]

with open(anchors_path) as f:
    anchors = f.readline()
    anchors = [float(x) for x in anchors.split(',')]
    anchors = np.array(anchors).reshape(-1, 2)

yolo_model = load_model(model_path)

# Verify model, anchors, and classes are compatible
num_classes = len(class_names)
num_anchors = len(anchors)

# Check if model is fully convolutional, assuming channel last order.
model_image_size = yolo_model.layers[0].input_shape[1:3]
is_fixed_size = model_image_size != (None, None)

# Generate colors for drawing bounding boxes.
hsv_tuples = [(x / len(class_names), 1., 1.)
              for x in range(len(class_names))]
colors = list(map(lambda x: colorsys.hsv_to_rgb(*x), hsv_tuples))
colors = list(
    map(lambda x: (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)),
        colors))
random.seed(10101)  # Fixed seed for consistent colors across runs.
random.shuffle(colors)  # Shuffle colors to decorrelate adjacent classes.
random.seed(None)  # Reset seed to default.

# Generate output tensor targets for filtered bounding boxes.
yolo_outputs = yolo_head(yolo_model.output, anchors, len(class_names))

input_image_shape = K.placeholder(shape=(2, ))
boxes, scores, classes = yolo_eval(
    yolo_outputs,
    input_image_shape,
    score_threshold = score_threshold,
    iou_threshold = iou_threshold)

capture = cv2.VideoCapture(file_name)

flameFPS = capture.get(cv2.CAP_PROP_FPS)
flameNum = capture.get(cv2.CAP_PROP_FRAME_COUNT)
Width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
Height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
flameSpan = 1.0 / flameFPS

nowFlame = 0

if file_name.rsplit('.', 1)[1] == 'avi':
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    print('avi')

if file_name.rsplit('.', 1)[1] == 'mp4':
    fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
    print('mp4')

VWriter = cv2.VideoWriter(output_path,fourcc, flameFPS, (Width, Height))
capture.set(cv2.CAP_PROP_POS_FRAMES, nowFlame)

while(capture.isOpened()):
    ret, frame = capture.read()

    cv_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    src_image_pil=Image.fromarray(cv_rgb)
    pil_normalize = src_image_pil.convert('RGB')
    image = pil_normalize

    if is_fixed_size:  # TODO: When resizing we can use minibatch input.
        resized_image = image.resize(
            tuple(reversed(model_image_size)), Image.BICUBIC)
        image_data = np.array(resized_image, dtype='float32')
    else:
        # Due to skip connection + max pooling in YOLO_v2, inputs must have
        # width and height as multiples of 32.
        new_image_size = (image.width - (image.width % 32),
                          image.height - (image.height % 32))
        resized_image = image.resize(new_image_size, Image.BICUBIC)
        image_data = np.array(resized_image, dtype='float32')

    image_data /= 255.
    image_data = np.expand_dims(image_data, 0)  # Add batch dimension.

    out_boxes, out_scores, out_classes = sess.run(
        [boxes, scores, classes],
        feed_dict={
            yolo_model.input: image_data,
            input_image_shape: [image.size[1], image.size[0]],
            K.learning_phase(): 0
        })

    font = ImageFont.truetype(
        font='YAD2K/font/FiraMono-Medium.otf',
        size=np.floor(3e-2 * image.size[1] + 0.5).astype('int32'))
    thickness = (image.size[0] + image.size[1]) // 300

    for i, c in reversed(list(enumerate(out_classes))):
        predicted_class = class_names[c]
        box = out_boxes[i]
        score = out_scores[i]

        label = '{} {:.2f}'.format(predicted_class, score)

        draw = ImageDraw.Draw(image)
        label_size = draw.textsize(label, font)

        top, left, bottom, right = box
        top = max(0, np.floor(top + 0.5).astype('int32'))
        left = max(0, np.floor(left + 0.5).astype('int32'))
        bottom = min(image.size[1], np.floor(bottom + 0.5).astype('int32'))
        right = min(image.size[0], np.floor(right + 0.5).astype('int32'))
        print("flame_number:{}, label:{}, center:({},{}), width:{}, height:{}, score:{:.3f}".format(nowFlame, label, (left + right)/2, (top + bottom)/2, right - left, bottom - top, score))
        #print(label, (left, top), (right, bottom))

        if top - label_size[1] >= 0:
            text_origin = np.array([left, top - label_size[1]])
        else:
            text_origin = np.array([left, top + 1])

        # My kingdom for a good redistributable image drawing library.

        for i in range(thickness):
            draw.rectangle(
                [left + i, top + i, right - i, bottom - i],
                outline=colors[c])
        draw.rectangle(
            [tuple(text_origin), tuple(text_origin + label_size)],
            fill=colors[c])
        draw.text(text_origin, label, fill=(0, 0, 0), font=font)
        del draw

    cv_output=np.asarray(image)
    cv_output = cv2.cvtColor(cv_output, cv2.COLOR_BGR2RGB)
    #cv2.imshow("view", cv_output)
    VWriter.write(cv_output)
    nowFlame += 1
    if nowFlame == flameNum :
        break

sess.close()
