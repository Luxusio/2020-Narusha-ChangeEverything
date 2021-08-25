import numpy as np
import tensorflow as tf
import torch
from tensorflow.keras import layers
from tensorflow_addons.layers import InstanceNormalization

physical_devices = tf.config.experimental.list_physical_devices('GPU')
for physical_device in physical_devices:
    tf.config.experimental.set_memory_growth(physical_device, True)


class ReflectionPadding2D(tf.keras.layers.Layer):
    def __init__(self, padding=1, **kwargs):
        super(ReflectionPadding2D, self).__init__(**kwargs)
        self.padding = padding

    def compute_output_shape(self, s):
        return s[0], s[1] + 2 * self.padding, s[2] + 2 * self.padding, s[3]

    def call(self, x):
        return tf.pad(x, [[0, 0], [self.padding, self.padding], [self.padding, self.padding], [0, 0], ], "REFLECT", )


class ConvLayer(tf.keras.layers.Layer):
    def __init__(self, channels, kernel_size=3, strides=1):
        super(ConvLayer, self).__init__()
        reflection_padding = kernel_size // 2
        self.reflection_pad = ReflectionPadding2D(reflection_padding)
        self.conv2d = layers.Conv2D(channels, kernel_size, strides=strides)

    def call(self, x):
        x = self.reflection_pad(x)
        x = self.conv2d(x)
        return x


class UpsampleConvLayer(tf.keras.layers.Layer):
    def __init__(self, channels, kernel_size=3, strides=1, upsample=2):
        super(UpsampleConvLayer, self).__init__()
        reflection_padding = kernel_size // 2
        self.reflection_pad = ReflectionPadding2D(reflection_padding)
        self.conv2d = layers.Conv2D(channels, kernel_size, strides=strides)
        self.up2d = layers.UpSampling2D(size=upsample)

    def call(self, x):
        x = self.up2d(x)
        x = self.reflection_pad(x)
        x = self.conv2d(x)
        return x


class ResidualBlock(tf.keras.Model):
    def __init__(self, channels, strides=1):
        super(ResidualBlock, self).__init__()
        self.conv1 = ConvLayer(channels, kernel_size=3, strides=strides)
        self.in1 = InstanceNormalization()
        self.conv2 = ConvLayer(channels, kernel_size=3, strides=strides)
        self.in2 = InstanceNormalization()

    def call(self, inputs):
        residual = inputs
        x = self.in1(self.conv1(inputs))
        x = tf.nn.relu(x)
        x = self.in2(self.conv2(x))
        x = x + residual
        return x


class TransformerNet(tf.keras.Model):
    def __init__(self):
        super(TransformerNet, self).__init__()

        self.conv1 = ConvLayer(16, kernel_size=9, strides=1)
        self.in1 = InstanceNormalization()

        self.conv2 = ConvLayer(32, kernel_size=3, strides=2)
        self.in2 = InstanceNormalization()

        self.conv3 = ConvLayer(64, kernel_size=3, strides=2)
        self.in3 = InstanceNormalization()

        self.res1 = ResidualBlock(64)
        self.res2 = ResidualBlock(64)
        self.res3 = ResidualBlock(64)
        self.res4 = ResidualBlock(64)
        self.res5 = ResidualBlock(64)

        self.deconv1 = UpsampleConvLayer(32, kernel_size=3, strides=1, upsample=2)
        self.in4 = InstanceNormalization()
        self.deconv2 = UpsampleConvLayer(16, kernel_size=3, strides=1, upsample=2)
        self.in5 = InstanceNormalization()
        self.deconv3 = ConvLayer(3, kernel_size=9, strides=1)

        self.relu = layers.ReLU()

    def call(self, x):
        x = self.relu(self.in1(self.conv1(x)))
        x = self.relu(self.in2(self.conv2(x)))
        x = self.relu(self.in3(self.conv3(x)))
        x = self.res1(x)
        x = self.res2(x)
        x = self.res3(x)
        x = self.res4(x)
        x = self.res5(x)
        x = self.relu(self.in4(self.deconv1(x)))
        x = self.relu(self.in5(self.deconv2(x)))
        x = self.deconv3(x)
        x = layers.Activation('tanh')(x)
        x = (x + 1) * 127.5
        return x


transformer = TransformerNet()

transformer.build((None, None, None, 3))

basepath = 'filter/'
facebasepath = 'fsgan/docs/examples/'
filter_name = 'transformer_1.h5'
# 전처리 끝


# 이게 필터 불러오는 코드
transformer.load_weights(basepath + filter_name)

import sys
import os
import threading
import cv2
import facefilter

from PyQt5 import uic, QtGui, QtWidgets
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QPixmap

form_class = uic.loadUiType("mainwindow.ui")[0]
filterDialog = uic.loadUiType("filterdialog.ui")[0]
image_class = uic.loadUiType("image_dialog.ui")[0]
running = True
count = 1
DIR_PATH = 'save/'
check = '.h5'
image_model = facefilter.model


class ImageWindow(QDialog, image_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.start()

    def start(self):
        imagFile_list = os.listdir(DIR_PATH)

        # ListWidget 생성
        for item in imagFile_list: self.imageListWidget.addItem(item)
        self.imageListWidget.itemClicked.connect(self.chkItemClicked)

    def chkItemClicked(self):
        imgfile = DIR_PATH + self.imageListWidget.currentItem().text()

        wh = self.selectImg.size()
        self.pixmap = QPixmap(imgfile)
        self.pixmap.scaled(self.selectImg.size())
        self.pixmap.load(imgfile)
        self.pixmap = self.pixmap.scaledToWidth(wh.width())
        self.selectImg.setPixmap(QPixmap(self.pixmap))


class MyWindow(QMainWindow, form_class):
    def __init__(self):
        global count
        super().__init__()
        self.setupUi(self)
        self.start()

        self.image_model = image_model

        self.saveButton.clicked.connect(self.save_changed)
        self.changeButton.clicked.connect(self.dialog_open)
        self.loadButton.clicked.connect(self.ImageDialog)

        save_path = "save/"
        file_list = os.listdir(save_path)

        if not file_list:
            count = 1
        else:
            fileString = os.path.splitext(file_list[-1])[0]
            count = int(fileString[-1]) + 1

    def dialog_open(self):
        print("dialog!")
        self.dialog = DialogWindow()
        print("exec!")
        self.dialog.exec_()
        print("selected")
        self.selected = self.dialog.selectedItems

    def save_changed(self, arg1):
        global count
        img = cv2.cvtColor(self.img_result, cv2.COLOR_BGR2RGB)
        filename = 'save/changed{}.jpg'.format(count)
        cv2.imwrite(filename, img)
        count += 1

        QtWidgets.QMessageBox.information(self, "저장 완료", filename + "로 저장되었습니다.")

    def ImageDialog(self):
        self.imageDialog = ImageWindow()
        self.imageDialog.show()

    def backImgFilter(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, c = img.shape

        np_image = np.array(img).copy().astype('float32') / 127.5 - 1

        self.img_result = transformer.predict(np_image[tf.newaxis, :, :, :])[0].astype('uint8')

        qImg = QtGui.QImage(img.data, w, h, w * c, QtGui.QImage.Format_RGB888)
        qImg2 = QtGui.QImage(self.img_result.data, w, h, w * c, QtGui.QImage.Format_RGB888)

        pixmap = QtGui.QPixmap.fromImage(qImg)
        pixmap2 = QtGui.QPixmap.fromImage(qImg2)

        self.originalVideo.setPixmap(pixmap)
        self.changedVideo.setPixmap(pixmap2)

    def faceFilter(self, img):
        #
        h, w, c = img.shape

        np_image = np.array(img).copy()

        with torch.no_grad():
            self.img_result = self.image_model(np_image)
        # self.img_result = cv2.cvtColor(self.img_result, cv2.COLOR_BGR2RGB)
        torch.cuda.empty_cache()

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qImg = QtGui.QImage(img.data, w, h, w * c, QtGui.QImage.Format_RGB888)
        qImg2 = QtGui.QImage(self.img_result.data, w, h, w * c, QtGui.QImage.Format_RGB888)

        pixmap = QtGui.QPixmap.fromImage(qImg)
        pixmap2 = QtGui.QPixmap.fromImage(qImg2)

        self.originalVideo.setPixmap(pixmap)
        self.changedVideo.setPixmap(pixmap2)

    def run(self):
        global running

        cap = cv2.VideoCapture(1)
        cap.set(3, 960)
        cap.set(4, 540)

        while running:
            ret, img = cap.read()
            if ret:
                if check == '.h5':
                    self.backImgFilter(img)
                elif check == '.mp4':
                    self.faceFilter(img)
            else:
                QtWidgets.QMessageBox.about(self.window(), "Error", "Cannot read frame.")
                print("cannot read frame.")
                break

        cap.release()
        print("Thread end")

    def start(self):
        global running
        running = True
        th = threading.Thread(target=self.run)
        th.daemon = True
        th.start()
        print("started")

    def stop(self):
        global running
        running = False
        print("stop")


class DialogWindow(QDialog, filterDialog):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.filter_list = ['젊은 미국 소녀, 댄스', '파도', '절규', '비오는날의 공주', '미노타우로스의 난파선', 'a muse',
                            '아포칼립스', 'Milky Way', '지금 불타고 있습니다.', '구성', '점묘화', '회상', '스케치',
                            '노을', '그날 저녁', '그랑자트섬의 일요일 오후', '퍼플 펑크', '별이 빛나는 밤', '감전중',
                            '아베 신조', '트럼프', '뷔', '시진핑', '슈가', '여동민', '허경영']
        # '문재인',
        self.filter_converter = {
            '젊은 미국 소녀, 댄스': 'transformer_1.h5',
            '파도': 'transformer_2.h5',
            '절규': 'transformer_3.h5',
            '비오는날의 공주': 'transformer_4.h5',
            '미노타우로스의 난파선': 'transformer_5.h5',
            'a muse': 'transformer_6.h5',
            '아포칼립스': 'transformer_7.h5',
            'Milky Way': 'transformer_9.h5',
            '지금 불타고 있습니다.': 'transformer_10.h5',
            '구성': 'transformer_11.h5',
            '점묘화': 'transformer_12.h5',
            '회상': 'transformer_13.h5',
            '스케치': 'transformer_14.h5',
            '노을': 'transformer_15.h5',
            '그날 저녁': 'transformer_16.h5',
            '그랑자트섬의 일요일 오후': 'transformer_18.h5',
            '퍼플 펑크': 'transformer_19.h5',
            '별이 빛나는 밤': 'transformer_20.h5',
            '감전중': 'transformer_21.h5',
            '문재인': 'moon.mp4',
            '아베 신조': 'shinzo_abe.mp4',
            '트럼프': 'trump.mp4',
            '뷔': 'V.mp4',
            '시진핑': 'xijinping.mp4',
            '슈가': '슈가.mp4',
            '여동민': '여동민.mp4',
            '허경영': '허경영.mp4'
        }

        for item in self.filter_list:
            listitem = QListWidgetItem(item)
            self.listWidget.addItem(listitem)

        self.selectedItems = None

        self.okButton.clicked.connect(self.ok)
        self.cancelButton.clicked.connect(self.cancel)

    def ok(self):
        global filter_name
        global check

        self.selectedItems = self.listWidget.currentItem().text()

        filter_name = self.filter_converter[self.selectedItems]
        

        check = os.path.splitext(filter_name)[1]

        if check == '.h5':
            transformer.load_weights(basepath + filter_name)
            try:
                self.close()
            except Exception as e:
                print("exception occured")
                print(e)
        elif check == '.mp4':
            facefilter.model.prepare(facebasepath + filter_name)
            try:
                self.close()
            except Exception as e:
                print("exception occured")
                print(e)

    def cancel(self):
        try:
            self.close()
        except Exception as e:
            print("exception occured")
            print(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    myWindow = MyWindow()
    myWindow.show()

    sys.exit(app.exec_())
