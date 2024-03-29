import codes.utils.evaluation as evaluation
import codes.utils.tensors_io as tensors_io
from codes.test_routines import get_only_segmentation, quick_seg_inst_test
import torch.optim as optim
import torch
import numpy as np
# import testing_routines


##################################################################################################################################
#                                                      TRAIN Network                                                             #
##################################################################################################################################
def train_semantic_segmentation_net(t_params, data_path_list, mask_path_list):
    print("Starting Training for Semantic Segmentation: " + t_params.network_name)
    net = t_params.net
    criterion = t_params.criterion_s

    device = t_params.device

    data_volume_list = []
    # Load Data Volume
    if(t_params.uint_16 is False):
        for data_path in data_path_list:
            data_volume_list.append((tensors_io.load_volume(data_path, scale=t_params.scale_p)).unsqueeze(0))
    else:
        for data_path in data_path_list:
            data_volume_list.append((tensors_io.load_fibers_uint16(data_path, scale=t_params.scale_p)).unsqueeze(0))

    if(t_params.cleaning_sangids is True):
        for i in range(len(data_volume_list)):
            data_volume_list[i][0, 0, ...] = tensors_io.clean_noise(data_volume_list[i][0, 0, ...], data_volume_list[i])

    if(t_params.cleaning is True):
        for i in range(len(data_volume_list)):
            data_volume_list[i] = tensors_io.normalize_dataset(data_volume_list[i])

    # Load Masks
    masks_list = []
    for mask_path in mask_path_list:
        masks_list.append(tensors_io.load_volume_uint16(mask_path, scale=t_params.scale_p).long().unsqueeze(0))

    # Optimizer and loss function
    optimizer = optim.Adam(net.parameters(), lr=t_params.lr)
    num_datasets = len(data_path_list)
    # Send the model to GPU
    print("Training for {} epochs".format(t_params.epochs))
    net = net.to(device)
    for epoch in range(t_params.epochs):
        print('Starting epoch {}/{}.'.format(epoch + 1, t_params.epochs))
        net.train()
        epoch_loss = 0
        seg_total_loss = 0
        for i in range(t_params.batch_size + 30):
            data_volume = data_volume_list[i % num_datasets]
            masks = masks_list[i % num_datasets]
            (mini_V, mini_M) = tensors_io.random_crop_3D_image_batched(data_volume, masks, t_params.cube_size, random_rotations=1)

            mini_V = mini_V.to(device)
            mini_M = mini_M.to(device)

            if(t_params.n_classes == 2):
                true_masks = (mini_M > 0).long()
            else:
                true_masks = mini_M.long()
            if(true_masks.max() == 0):
                continue

            segmentation_output = net(mini_V)
            s_loss = criterion(true_masks, segmentation_output)

            epoch_loss += s_loss.item()
            seg_total_loss += s_loss.item()

            optimizer.zero_grad()
            s_loss.backward()
            optimizer.step()

        if(epoch % 10 == 0):
            print('Dict Saved')
            torch.save(net.state_dict(), t_params.net_weights_dir[0])
            _, final_pred = segmentation_output.max(1)
            evaluation.evaluate_segmentation(final_pred, mini_M)

            if(t_params.debug is True):
                tensors_io.save_subvolume_instances(mini_V, final_pred, "results/debug_seg_training")

        print("loss: " + str(epoch_loss / i))
        if(epoch_loss / i < 0.01):
            break
    # save dictionary
    torch.save(net.state_dict(), t_params.net_weights_dir[0])
    evaluation.evaluate_segmentation(final_pred, mini_M)
    print("FINISHED TRAINING")


def train_instance_segmentation_net(t_params, data_path_list, mask_path_list):
    print("Starting Training for instance segmentation for " + t_params.network_name)
    print("Window Size: {}. N Classes: {} N Embeddings: {} N Dim{}".format(t_params.cube_size, t_params.n_classes, t_params.n_embeddings, t_params.ndims))
    net_i = t_params.net_i
    net_s = t_params.net
    criterion_i = t_params.criterion_i

    device = t_params.device

    data_volume_list = []
    # Load Data Volume
    if(t_params.uint_16 is False):
        for data_path in data_path_list:
            data_volume_list.append((tensors_io.load_volume(data_path, scale=t_params.scale_p)).unsqueeze(0))
    else:
        for data_path in data_path_list:
            data_volume_list.append((tensors_io.load_fibers_uint16(data_path, scale=t_params.scale_p)).unsqueeze(0))

    if(t_params.cleaning_sangids is True):
        for i in range(len(data_volume_list)):
            data_volume_list[i][0, 0, ...] = tensors_io.clean_noise(data_volume_list[i][0, 0, ...], data_volume_list[i])

    if(t_params.cleaning is True):
        for i in range(len(data_volume_list)):
            data_volume_list[i] = tensors_io.normalize_dataset(data_volume_list[i])
    # Load Masks
    masks_list = []
    for mask_path in mask_path_list:
        masks_list.append(tensors_io.load_volume_uint16(mask_path, scale=t_params.scale_p).long().unsqueeze(0))

    # Optimizer and loss function
    optimizer = optim.Adam(net_i.parameters(), lr=t_params.lr)
    num_datasets = len(data_path_list)
    # Send the model to GPU
    net_i = net_i.to(device)
    net_s = net_s.to(device)

    for epoch in range(t_params.epochs_instance):
        print('Starting epoch {}/{}.'.format(epoch + 1, t_params.epochs_instance))
        net_i.train()
        epoch_loss = 0
        emb_total_loss = 0
        seg_total_loss = 0
        for i in range(t_params.batch_size + 30):
            data_volume = data_volume_list[i % num_datasets]
            masks = masks_list[i % num_datasets]
            (mini_V, mini_M) = tensors_io.random_crop_3D_image_batched(data_volume, masks, t_params.cube_size)

            mini_V = mini_V.to(device)
            true_masks = mini_M.to(device)

            # Evaluate Net
            embedding_output = net_i(mini_V)
            loss = criterion_i(embedding_output, true_masks, t_params)

            if(loss is None):
                continue
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            emb_total_loss += loss.item()

        if((epoch) % 10 == 0 and epoch > 10):
            torch.save(net_i.state_dict(), t_params.net_weights_dir[1])
            # quick_seg_inst_test(t_params, mini_V, mini_M)
            print('Dict Saved')
        print("loss: " + str(epoch_loss / i) + ", e_loss: " + str(emb_total_loss / i) + ", s_loss: " + str(seg_total_loss / i))
    # save dictionary
    torch.save(net_i.state_dict(), t_params.net_weights_dir[1])
    print("FINISHED TRAINING")


def train_multitask_loss_net(t_params, data_path_list, mask_path_list):
    print("Starting Training for multitask loss with " + t_params.network_name + " in device " + str(t_params.device))
    net_mt = t_params.net
    criterion_i = t_params.criterion_i
    criterion_s = t_params.criterion_s

    device = t_params.device

    data_volume_list = []
    # Load Data Volume
    if(t_params.uint_16 is False):
        for data_path in data_path_list:
            data_volume_list.append((tensors_io.load_volume(data_path, scale=t_params.scale_p)).unsqueeze(0))
    else:
        for data_path in data_path_list:
            data_volume_list.append((tensors_io.load_fibers_uint16(data_path, scale=t_params.scale_p)).unsqueeze(0))

    if(t_params.cleaning_sangids is True):
        for i in range(len(data_volume_list)):
            data_volume_list[i][0, 0, ...] = tensors_io.clean_noise(data_volume_list[i][0, 0, ...], data_volume_list[i])

    if(t_params.cleaning is True):
        for i in range(len(data_volume_list)):
            data_volume_list[i] = tensors_io.normalize_dataset(data_volume_list[i])

    # Load Masks
    masks_list = []
    for mask_path in mask_path_list:
        masks_list.append(tensors_io.load_volume_uint16(mask_path, scale=t_params.scale_p).long().unsqueeze(0))

    # Optimizer and loss function
    optimizer = optim.Adam(net_mt.parameters(), lr=t_params.lr)
    num_datasets = len(data_path_list)
    # Send the model to GPU
    net_mt = net_mt.to(device)

    for epoch in range(t_params.epochs_instance):
        print('Starting epoch {}/{}.'.format(epoch + 1, t_params.epochs_instance))
        net_mt.train()
        epoch_loss = 0
        emb_total_loss = 0
        seg_total_loss = 0
        for i in range(t_params.batch_size + 30):
            data_volume = data_volume_list[i % num_datasets]
            masks = masks_list[i % num_datasets]

            (mini_V, mini_M) = tensors_io.random_crop_3D_image_batched(data_volume, masks, t_params.cube_size)
            mini_V = mini_V.to(device)
            true_masks = mini_M.to(device)
            if(true_masks.max() == 0):
                sigma0 = torch.tensor(1)
                sigma1 = torch.tensor(1)
                continue
            # Evaluate Net
            outputs = net_mt(mini_V)

            if(t_params.network_name == "unet_double"):
                segmentation_output = outputs[0]
                embedding_output = outputs[1]
                s_loss = criterion_s((true_masks > 0).long(), segmentation_output)
                e_loss = criterion_i(embedding_output, true_masks, t_params)
                if(e_loss is None or s_loss is None):
                    continue
                total_loss = t_params.alpha_seg * s_loss + t_params.alpha_emb * e_loss
                sigma0 = torch.tensor(t_params.alpha_seg)
                sigma1 = torch.tensor(t_params.alpha_emb)
            else:
                total_loss, s_loss, e_loss, sigma0, sigma1 = t_params.criterion(outputs, true_masks, t_params)

            optimizer.zero_grad()
            total_loss.backward()
            optimizer.step()

            epoch_loss += total_loss.item()
            emb_total_loss += e_loss.item()
            seg_total_loss += s_loss.item()

        if((epoch) % 10 == 0):
            t_params.training_numbers['total_loss'].append(epoch_loss)
            t_params.training_numbers['seg_loss'].append(seg_total_loss)
            t_params.training_numbers['offset_loss'].append(emb_total_loss)
            t_params.training_numbers['sigma0'].append(sigma0.cpu().item())
            t_params.training_numbers['sigma1'].append(sigma1.cpu().item())
            torch.save(net_mt.state_dict(), t_params.net_weights_dir[0])
            np.save(t_params.net_train_dict_dir, t_params.training_numbers)

            # mini_V_or, final_pred, final_fibers, mini_M, seg_eval, inst_eval, inst_eval_objectwise = quick_seg_inst_test(t_params)
            # t_params.training_numbers['seg_f1_train'].append(seg_eval)
            # t_params.training_numbers['Ra_train'].append(inst_eval)
            print('Dict Saved')

        print("loss: " + str(epoch_loss / i) + ", e_loss: " + str(emb_total_loss / i) + ", s_loss: " + str(seg_total_loss / i) + ", sigma0:" + str(sigma0.cpu().item()) + ", sigma1:" + str(sigma1.cpu().item()))
    # save dictionary
    torch.save(net_mt.state_dict(), t_params.net_weights_dir[0])
    print("FINISHED TRAINING")


def train_r_net_embedded_offset(net, net_s, data_path, mask_path, data_list2, mask_list2, n_classes=2, n_embedded=16, cube_size=32, epochs=10, batch_size=1, Patches_per_Epoch=30, scale_p=2, pre_trained=False, device=None):
    print("Starting Offset Training...")
    GPU_YES = torch.cuda.is_available()
    if(device is None):
        device = torch.device("cuda:0" if GPU_YES else "cpu")

    if(pre_trained):
        print("Loading pre-trained-weights")
        net.load_state_dict(torch.load('info_files/r_net_offset.pth'))

    # Load Data Volume
    data_volume = tensors_io.load_volume(data_path, scale=scale_p)
    data_volume[0, ...] = tensors_io.clean_noise(data_volume[0, ...], data_path)
    data_volume = data_volume.unsqueeze(0)

    # Load Data Volume2
    temp_volume = tensors_io.load_volume(data_list2[0], scale=scale_p)
    temp_volume[0, ...] = tensors_io.clean_noise(temp_volume[0, ...], data_list2[0])

    masks = tensors_io.load_volume_uint16(mask_path, scale=scale_p).long().unsqueeze(0)

    (ch2, rows2, cols2, depth2) = temp_volume.shape
    num_datasets = len(data_list2)

    data_volume2 = torch.zeros(num_datasets, ch2, rows2, cols2, depth2)
    masks2 = torch.zeros(num_datasets, ch2, rows2, cols2, depth2, dtype=torch.long)
    data_volume2[0, ...] = temp_volume
    masks2[0, ...] = tensors_io.load_volume_uint16(mask_list2[0], scale=scale_p).long()
    for counter in range(1, num_datasets):
        temp_volume = tensors_io.load_volume(data_list2[counter], scale=scale_p)
        temp_volume[0, ...] = tensors_io.clean_noise(temp_volume[0, ...], data_list2[counter])
        data_volume2[counter, ...] = temp_volume

        masks2[counter, ...] = tensors_io.load_volume_uint16(mask_list2[counter], scale=scale_p).long()

    [_, channels, rows, cols, slices] = data_volume.size()

    # Optimizer and loss function
    optimizer = optim.SGD(net.parameters(), lr=0.00001, momentum=0.9, weight_decay=0.0005)


    # Send the model to CPU or GPU
    net = net.to(device)
    for epoch in range(epochs):
        print('Starting epoch {}/{}.'.format(epoch + 1, epochs))
        net.train()
        epoch_loss = 0
        emb_total_loss = 0
        seg_total_loss = 0
        for i in range(Patches_per_Epoch):
            if(i % (num_datasets + 1) == 0):
                (mini_V, mini_M) = tensors_io.random_crop_3D_image_batched(data_volume, masks, cube_size)
            else:
                number = i % num_datasets
                vol = data_volume2[number, ...].unsqueeze(0)
                msk = masks2[number, ...].unsqueeze(0)
                (mini_V, mini_M) = tensors_io.random_crop_3D_image_batched(vol, msk, cube_size)

            mini_V = mini_V.to(device)
            true_masks = mini_M.to(device)

            # Evaluate Net
            embedding_output = net(mini_V)

            loss = embedded_geometric_loss_coords(embedding_output, true_masks)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            emb_total_loss += loss.item()

        if((epoch) % 10 == 0 and epoch > -1):
            torch.save(net.state_dict(), "info_files/r_net_offset.pth")
            # save_data(embedding_output, true_masks, epoch)
            print('Dict Saved')
        print("loss: " + str(epoch_loss / i) + ", e_loss: " + str(emb_total_loss / i) + ", s_loss: " + str(seg_total_loss / i))
    # save dictionary
    torch.save(net.state_dict(), "info_files/r_net_offset.pth")
    print("FINISHED TRAINING")

