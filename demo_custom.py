import time
import os
from torch.autograd import Variable
import math
import torch

import random
import numpy as np
import numpy
import networks
from my_args import  args

from scipy.misc import imread, imsave, imresize
from AverageMeter import  *

import gc

torch.backends.cudnn.benchmark = True # to speed up the


DO_MiddleBurryOther = True
MB_Other_DATA = "/Date4/hpc/MM_stuff_icra/rgb_frames/"
MB_Other_RESULT = "./ruralscapes/"
MB_Other_GT = "/Date4/hpc/MM_stuff_icra/rgb_frames/"
if not os.path.exists(MB_Other_RESULT):
    os.mkdir(MB_Other_RESULT)



model = networks.__dict__[args.netName](channel=args.channels,
                            filter_size = args.filter_size ,
                            timestep=args.time_step,
                            training=False)


def image_translated_with_flow(rgb_1,flow):
    u, v = flow
    #print(u.shape, v.shape)
    u=np.squeeze(u)
    v=np.squeeze(v)
    rgb_2_from_rgb_1_with_flow = np.zeros_like(rgb_1)
    for x in range(rgb_1.shape[0]):
        for y in range(rgb_1.shape[1]):
            displacement_x = u[x, y]
            displacement_y = v[x, y]
            try:
                #print(x+displacement_x, y-displacement_y)
                if int(x-displacement_y) > 0 and int(y+displacement_x) > 0:
                    rgb_2_from_rgb_1_with_flow[int(x-displacement_y), int(y+displacement_x)] = rgb_1[x,y]
            except:
                pass
    return rgb_2_from_rgb_1_with_flow



if args.use_cuda:
    model = model.cuda()

args.SAVED_MODEL = './model_weights/best.pth'
if os.path.exists(args.SAVED_MODEL):
    print("The testing model weight is: " + args.SAVED_MODEL)
    if not args.use_cuda:
        pretrained_dict = torch.load(args.SAVED_MODEL, map_location=lambda storage, loc: storage)
        # model.load_state_dict(torch.load(args.SAVED_MODEL, map_location=lambda storage, loc: storage))
    else:
        pretrained_dict = torch.load(args.SAVED_MODEL)
        # model.load_state_dict(torch.load(args.SAVED_MODEL))

    model_dict = model.state_dict()
    # 1. filter out unnecessary keys
    pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
    # 2. overwrite entries in the existing state dict
    model_dict.update(pretrained_dict)
    # 3. load the new state dict
    model.load_state_dict(model_dict)
    # 4. release the pretrained dict for saving memory
    pretrained_dict = []
else:
    print("*****************************************************************")
    print("**** We don't load any trained weights **************************")
    print("*****************************************************************")
torch.set_grad_enabled(False)

model = model.eval() # deploy mode

torch.set_grad_enabled(False)

use_cuda=args.use_cuda
save_which=args.save_which
dtype = args.dtype
unique_id =str(random.randint(0, 100000))
print("The unique id for current testing is: " + str(unique_id))

OUT_SIZE = (780, 1280)
OUT_SIZE = (1080, 1980)

interp_error = AverageMeter()
if DO_MiddleBurryOther:
    subdir = os.listdir(MB_Other_DATA)
    gen_dir = os.path.join(MB_Other_RESULT, unique_id)
    os.mkdir(gen_dir)

    tot_timer = AverageMeter()
    proc_timer = AverageMeter()
    end = time.time()
    for dir in subdir:
        print(dir)
        os.mkdir(os.path.join(gen_dir, dir))
        arguments_strFirst = os.path.join(MB_Other_DATA, dir, dir.replace("_all", "")+"_000000.jpg")
        arguments_strSecond = os.path.join(MB_Other_DATA, dir, dir.replace("_all", "")+"_000003.jpg")
        arguments_strOut = os.path.join(gen_dir, dir, dir.replace("_all", "")+"_i_000002.jpg")
        gt_path = os.path.join(MB_Other_GT, dir, dir.replace("_all", "")+"_000002.jpg")

        print('memory before inference', torch.cuda.memory_allocated()
        
        imgL_o = imresize(imread(arguments_strFirst), OUT_SIZE)
        imgR_o = imresize(imread(arguments_strSecond), OUT_SIZE)
        X0 =  torch.from_numpy( np.transpose(imgL_o, (2,0,1)).astype("float32")/ 255.0).type(dtype)
        X1 =  torch.from_numpy( np.transpose(imgR_o, (2,0,1)).astype("float32")/ 255.0).type(dtype)


        y_ = torch.FloatTensor()

        assert (X0.size(1) == X1.size(1))
        assert (X0.size(2) == X1.size(2))

        intWidth = X0.size(2)
        intHeight = X0.size(1)
        channel = X0.size(0)
        if not channel == 3:
            continue

        if intWidth != ((intWidth >> 7) << 7):
            intWidth_pad = (((intWidth >> 7) + 1) << 7)  # more than necessary
            intPaddingLeft =int(( intWidth_pad - intWidth)/2)
            intPaddingRight = intWidth_pad - intWidth - intPaddingLeft
        else:
            intWidth_pad = intWidth
            intPaddingLeft = 32
            intPaddingRight= 32

        if intHeight != ((intHeight >> 7) << 7):
            intHeight_pad = (((intHeight >> 7) + 1) << 7)  # more than necessary
            intPaddingTop = int((intHeight_pad - intHeight) / 2)
            intPaddingBottom = intHeight_pad - intHeight - intPaddingTop
        else:
            intHeight_pad = intHeight
            intPaddingTop = 32
            intPaddingBottom = 32

        pader = torch.nn.ReplicationPad2d([intPaddingLeft, intPaddingRight , intPaddingTop, intPaddingBottom])

        X0 = Variable(torch.unsqueeze(X0,0))
        X1 = Variable(torch.unsqueeze(X1,0))
        X0 = pader(X0)
        X1 = pader(X1)

        if use_cuda:
            X0 = X0.cuda()
            X1 = X1.cuda()
        proc_end = time.time()

        y_s,offset,filter = model(torch.stack((X0, X1),dim = 0))
                
        print('memory after inference', torch.cuda.memory_allocated())

        


        y_ = y_s[save_which]

        proc_timer.update(time.time() -proc_end)
        tot_timer.update(time.time() - end)
        end  = time.time()
        print("*****************current image process time \t " + str(time.time()-proc_end )+"s ******************" )
        if use_cuda:
            X0 = X0.data.cpu().numpy()
            y_ = y_.data.cpu().numpy()
            offset = [offset_i.data.cpu().numpy() for offset_i in offset]
            filter = [filter_i.data.cpu().numpy() for filter_i in filter]  if filter[0] is not None else None
            X1 = X1.data.cpu().numpy()
        else:
            X0 = X0.data.numpy()
            y_ = y_.data.numpy()
            offset = [offset_i.data.numpy() for offset_i in offset]
            filter = [filter_i.data.numpy() for filter_i in filter]
            X1 = X1.data.numpy()


        X0 = np.transpose(255.0 * X0.clip(0,1.0)[0, :, intPaddingTop:intPaddingTop+intHeight, intPaddingLeft: intPaddingLeft+intWidth], (1, 2, 0))
        y_ = np.transpose(255.0 * y_.clip(0,1.0)[0, :, intPaddingTop:intPaddingTop+intHeight, intPaddingLeft: intPaddingLeft+intWidth], (1, 2, 0))
        offset = [np.transpose(offset_i[0, :, intPaddingTop:intPaddingTop+intHeight, intPaddingLeft: intPaddingLeft+intWidth], (1, 2, 0)) for offset_i in offset]
        
        print('os', len(offset))
        filter = [np.transpose(
            filter_i[0, :, intPaddingTop:intPaddingTop + intHeight, intPaddingLeft: intPaddingLeft + intWidth],
            (1, 2, 0)) for filter_i in filter]  if filter is not None else None
        X1 = np.transpose(255.0 * X1.clip(0,1.0)[0, :, intPaddingTop:intPaddingTop+intHeight, intPaddingLeft: intPaddingLeft+intWidth], (1, 2, 0))

        print('memory after empty cache', torch.cuda.memory_allocated())


        imsave(arguments_strOut, np.round(y_).astype(numpy.uint8))
        
        
        del X0, X1, y_s,offset,filter, y_
        gc.collect()
        torch.cuda.empty_cache()
        
        """

        rec_rgb =  imresize(imread(arguments_strOut), OUT_SIZE)
        gt_rgb = imresize(imread(gt_path), OUT_SIZE)

        diff_rgb = 128.0 + rec_rgb - gt_rgb
        avg_interp_error_abs = np.mean(np.abs(diff_rgb - 128.0))

        interp_error.update(avg_interp_error_abs, 1)

        mse = numpy.mean((diff_rgb - 128.0) ** 2)

        PIXEL_MAX = 255.0
        psnr = 20 * math.log10(PIXEL_MAX / math.sqrt(mse))

        print("interpolation error / PSNR : " + str(round(avg_interp_error_abs,4)) + " / " + str(round(psnr,4)))
        metrics = "The average interpolation error / PSNR for all images are : " + str(round(interp_error.avg, 4))
        print(metrics)
        """