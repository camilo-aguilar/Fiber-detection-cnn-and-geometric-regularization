from .unet_parts import up, down, outconv, inconv
import torch.nn as nn
import torch


class UNet_double(nn.Module):
    def __init__(self, n_channels, n_classes_d1, n_classes_d2, num_dims=64):
        super(UNet_double, self).__init__()
        self.n_classe = n_classes_d1
        self.n_embeddings = n_classes_d2
        # Encoder
        self.inc = inconv(n_channels, num_dims)
        self.down1 = down(num_dims * 1, num_dims * 2)
        self.down2 = down(num_dims * 2, num_dims * 4)
        self.down3 = down(num_dims * 4, num_dims * 8)
        self.down4 = down(num_dims * 8, num_dims * 8)

        # Decoder
        self.up1 = up(num_dims * 16, num_dims * 4)
        self.up2 = up(num_dims * 8, num_dims * 2)
        self.up3 = up(num_dims * 4, num_dims * 1)
        self.up4 = up(num_dims * 2, num_dims * 1)
        self.out_d1 = outconv(num_dims, n_classes_d1)
        self.out_d2 = outconv(num_dims, n_classes_d2)

    def forward(self, x):
        # Encoder
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)

        # Decoder1
        x_d1 = self.up1(x5, x4)
        x_d1 = self.up2(x_d1, x3)
        x_d1 = self.up3(x_d1, x2)
        x_d1 = self.up4(x_d1, x1)
        x_d1 = self.out_d1(x_d1)

        # Decoder2
        x_d2 = self.up1(x5, x4)
        x_d2 = self.up2(x_d2, x3)
        x_d2 = self.up3(x_d2, x2)
        x_d2 = self.up4(x_d2, x1)
        x_d2 = self.out_d2(x_d2)

        return [x_d1, x_d2]

    def forward_inference(self, x, params_t):
        outputs = self(x)

        masks_probs = nn.functional.softmax(outputs[0], dim=1).float()
        _, final_pred = masks_probs.max(1)

        embedding_output = outputs[1].permute(0, 2, 3, 4, 1).contiguous().view(-1, self.n_embeddings)

        # Check only segmented pixels
        object_indexes = (final_pred > 0).long().view(-1).nonzero()
        if(len(object_indexes) == 0):
            return(None)
        object_pixels = torch.gather(embedding_output, 0, object_indexes.repeat(1, self.n_embeddings))

        # Vectorize and make it numpy
        X = object_pixels.detach().cpu().numpy()
        labels = params_t.clustering(X)

        # Convert back to space domain
        space_labels = torch.zeros_like(final_pred.view(-1))
        space_labels[object_indexes] = torch.from_numpy(labels).unsqueeze(1).to(params_t.device) + 2
        space_labels = space_labels.view(x.shape)

        return final_pred, space_labels
