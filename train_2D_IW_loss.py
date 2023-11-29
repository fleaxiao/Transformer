# Import necessary packages
import random
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import matplotlib.pyplot as plt

# Hyperparameters
NUM_EPOCH = 20 #! 2000
BATCH_SIZE = 256
LR_INI = 1e-4
WEIGHT_DECAY = 1e-7
DECAY_EPOCH = 100
DECAY_RATIO = 0.95

coef = 1

# Neural Network Structure
input_size = 13
output_size = 12
hidden_size = 100 #! 1000
hidden_layers = 3 #! 6

# Define model structures and functions
class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
   
        # Input layer
        layers = [nn.Linear(input_size, hidden_size), nn.ReLU()] 

        # Hidden layers
        for _ in range(hidden_layers):
            layers.append(nn.Linear(hidden_size, hidden_size))
            layers.append(nn.ReLU())
        
        # Output layer
        layers.append(nn.Linear(hidden_size, output_size))
        
        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

class myLoss(nn.Module):
    def __init__(self):
        super(myLoss, self).__init__()

    def forward(self, outputs, labels):
        # loss = torch.sum((outputs[labels != 0] - labels[labels != 0])**2) / labels.numel()
        loss = torch.mean((outputs[labels != 0] - labels[labels != 0])**2)
        return loss


# Load the datasheet
def get_dataset(adr):
    df = pd.read_csv(adr, header=None)
    
    # preprocess
    inputs = df.iloc[:13, 0:].values
    inputs[:2, 0:] = df.iloc[:2, 0:].values/10
    outputs = df.iloc[13:25, 0:].values
    outputs[:12, 0:] = outputs[:12, 0:]*coef
    outputs = np.where(outputs <= 0, 1e-10, outputs) 
    outputs[outputs == 0] = 1

    # log tranfer
    inputs = np.log10(inputs)
    outputs = np.log10(outputs)

    # normalization
    inputs_max = np.max(inputs, axis=1)
    inputs_min = np.min(inputs, axis=1)
    outputs_max = np.max(outputs, axis=1)
    outputs_min = np.min(outputs, axis=1)
    inputs = (inputs - inputs_min[:, np.newaxis]) / (inputs_max - inputs_min)[:, np.newaxis]
    outputs = (outputs - outputs_min[:, np.newaxis]) / (outputs_max - outputs_min)[:, np.newaxis]
    np.savetxt("dataset.csv", outputs, delimiter=',')

    # tensor transfer
    inputs = inputs.T
    outputs = outputs.T
    outputs_max = outputs_max.T
    outputs_min = outputs_min.T

    input_tensor = torch.tensor(inputs, dtype=torch.float32)
    output_tensor = torch.tensor(outputs, dtype=torch.float32)
   
    return torch.utils.data.TensorDataset(input_tensor, output_tensor), outputs_max, outputs_min

# Config the model training
def main():

    # Reproducibility
    random.seed(1)
    np.random.seed(1)
    torch.manual_seed(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # Check whether GPU is available
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print("Now this program runs on cuda")
    else:
        device = torch.device("cpu")
        print("Now this program runs on cpu")

    # Load and spit dataset
    dataset, outputs_max, outputs_min = get_dataset('testset_1w_IW.csv') #! Change to 10w datasheet when placed in Snellius 
    train_size = int(0.75 * len(dataset)) 
    valid_size = len(dataset) - train_size
    train_dataset, valid_dataset = torch.utils.data.random_split(dataset, [train_size, valid_size])
    test_dataset, test_outputs_max, test_outputs_min = get_dataset('testset_1w_IW.csv')
    if torch.cuda.is_available():
        kwargs = {'num_workers': 0, 'pin_memory': True, 'pin_memory_device': "cuda"}
    else:
        kwargs = {'num_workers': 0, 'pin_memory': True}
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, **kwargs)
    valid_loader = torch.utils.data.DataLoader(valid_dataset, batch_size=BATCH_SIZE, shuffle=True, **kwargs)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False, **kwargs)
    
    # Setup network
    net = Net().to(device)

    # Log the number of parameters
    with open('logfile.txt','w', encoding='utf-8') as f:
        f.write(f"Number of parameters: {count_parameters(net)}\n")

    # Setup optimizer
    criterion = myLoss()
    # criterion = nn.MSELoss()
    optimizer = optim.Adam(net.parameters(), lr=LR_INI, weight_decay=WEIGHT_DECAY) 
    
    # Train the network
    for epoch_i in range(NUM_EPOCH):

        # Train for one epoch
        epoch_train_loss = 0
        net.train()
        optimizer.param_groups[0]['lr'] = LR_INI* (DECAY_RATIO ** (0+ epoch_i // DECAY_EPOCH))
        
        for inputs, labels in train_loader:
            optimizer.zero_grad()
            outputs = net(inputs.to(device))
            loss = criterion(outputs, labels.to(device))
            loss.backward()
            optimizer.step()

            epoch_train_loss += loss.item()
        
        # Compute Validation Loss
        with torch.no_grad():
            epoch_valid_loss = 0
            for inputs, labels in valid_loader:
                outputs = net(inputs.to(device))
                loss = criterion(outputs, labels.to(device))
                
                epoch_valid_loss += loss.item()

        if (epoch_i+1)%100 == 0:
            print(f"Epoch {epoch_i+1:2d} "
                f"Train {epoch_train_loss / len(train_dataset) * 1e5:.5f} "
                f"Valid {epoch_valid_loss / len(valid_dataset) * 1e5:.5f} "
                f"Learning Rate {optimizer.param_groups[0]['lr']}")
            with open('logfile.txt','a', encoding='utf-8') as f:
                print(f"Epoch {epoch_i+1:2d} "
                f"Train {epoch_train_loss / len(train_dataset) * 1e5:.5f} "
                f"Valid {epoch_valid_loss / len(valid_dataset) * 1e5:.5f} "
                f"Learning Rate {optimizer.param_groups[0]['lr']}",file=f)

    # Save the model parameters
    torch.save(net.state_dict(), "Model_2D_IW_loss.pth")
    print("Training finished! Model is saved!")

    # Evaluation
    net.eval()
    x_meas = []
    y_meas = []
    y_pred = []
    with torch.no_grad():
        for inputs, labels in test_loader:
            y_pred.append(net(inputs.to(device)))
            y_meas.append(labels.to(device))
            x_meas.append(inputs)

    y_meas = torch.cat(y_meas, dim=0)
    y_pred = torch.cat(y_pred, dim=0)
    print(f"Test Loss: {F.mse_loss(y_meas, y_pred).item() / len(test_dataset) * 1e5:.5f}")  # f denotes formatting string
    
    # tensor is transferred to numpy
    yy_pred = y_pred.cpu().numpy()
    yy_meas = y_meas.cpu().numpy()
    yy_pred = yy_pred * (test_outputs_max - test_outputs_min)[np.newaxis,:] + test_outputs_min[np.newaxis,:]
    yy_meas = yy_meas * (test_outputs_max - test_outputs_min)[np.newaxis,:] + test_outputs_min[np.newaxis,:]

    yy_pred = 10**yy_pred
    yy_meas = 10**yy_meas
    np.savetxt("yy_meas.csv", yy_meas, delimiter=',')
    
    # Relative Error
    Error_re = np.zeros_like(yy_meas)
    Error_re[yy_meas != 1e-10] = abs(yy_pred[yy_meas != 1e-10] - yy_meas[yy_meas != 1e-10]) / abs(yy_meas[yy_meas != 1e-10]) * 100

    Error_re_avg = np.mean(Error_re)
    Error_re_rms = np.sqrt(np.mean(Error_re ** 2))
    Error_re_max = np.max(Error_re)
    print(f"Relative Error: {Error_re_avg:.8f}%")
    print(f"RMS Error: {Error_re_rms:.8f}%")
    print(f"MAX Error: {Error_re_max:.8f}%")
   
    # Visualization
    Error_Rac_Ls = 0
    Error_Rac_Lp = 0
     
    colors = plt.cm.viridis(np.linspace(0, 1, Error_re.shape[1]))
    bindwidth = 1e2

    #TODO Could change to "bins=np.arange(0, Error_re[:,i].max() + binwidth, binwidth)" when the erro is less than 10%
    plt.figure(figsize=(8, 5))
    for i in range (int(Error_re.shape[1]/2)):
        plt.hist(Error_re[:,i], bins=20, density=True, alpha=0.6, color=colors[i], edgecolor='black')
        Error_Rac_Ls += np.sum(Error_re[:,i] > 5)
    plt.title('Rac Error Distribution in Inner Winding')
    plt.xlabel('Error(%)')
    plt.ylabel('Distribution')
    plt.legend(labels=['inner_layer_1','inner_layer_2','inner_layer_3','inner_layer_4','inner_layer_5','inner_layer_6'])
    plt.grid()
    plt.savefig('figs/Fig_Rac_Ls.png',dpi=600)

    plt.figure(figsize=(8, 5))
    for i in range (int(Error_re.shape[1]/2), int(Error_re.shape[1])):
        plt.hist(Error_re[:,i], bins=20, density=True, alpha=0.6, color=colors[i], edgecolor='black') 
        Error_Rac_Lp += np.sum(Error_re[:,i] > 5)
    plt.title('Rac Error Distribution in Outer Winding')
    plt.xlabel('Error(%)')
    plt.ylabel('Distribution')
    plt.legend(labels=['outer_layer_1','outer_layer_2','outer_layer_3','outer_layer_4','outer_layer_5','outer_layer_6'])
    plt.grid()
    plt.savefig('figs/Fig_Rac_Lp.png',dpi=600)

    print(f"Number of Rac errors greater than 5% in inner winding: {Error_Rac_Ls}")
    print(f"Number of Rac errors greater than 5% in outer winding: {Error_Rac_Lp}")

    # plt.show()

if __name__ == "__main__":
    main()