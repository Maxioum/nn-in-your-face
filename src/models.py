from __future__ import annotations

import torch
import torch.nn as nn


class SkipConn(nn.Module):
	""" 
	Linear torch model with skip connections between every hidden layer\
	as well as the original input appended to every layer.\
	Because of this, each hidden layer contains `2*hidden_size+init_size` params\
	due to skip connections.
	Uses relu activations and one final sigmoid activation.

	Parameters: 
	hidden_size (float): number of non-skip parameters per hidden layer
	num_hidden_layers (float): number of hidden layers
	"""
	def __init__(self, hidden_size=100, num_hidden_layers=7, init_size=2, linmap: CenteredLinearMap = None, activation: nn.Module = nn.GELU, use_cuda: bool = True):
		super(SkipConn,self).__init__()
		out_size = hidden_size

		self.inLayer = nn.Linear(init_size, out_size)
		self.activation = activation()
		hidden = []
		for i in range(num_hidden_layers):
			in_size = out_size*2 + init_size if i>0 else out_size + init_size
			hidden.append(nn.Linear(in_size, out_size))
		self.hidden = nn.ModuleList(hidden)
		self.outLayer = nn.Linear(out_size*2+init_size, 1)
		self.tanh = nn.Tanh()
		self.sig = nn.Sigmoid()
		self._linmap = linmap
		self.use_cuda = use_cuda
		if use_cuda:
			self.cuda()

	def forward(self, x):
		if self._linmap:
			x = self._linmap.map(x)
		
		cur = self.activation(self.inLayer(x))
		prev = torch.tensor([])
		if self.use_cuda:
			prev = prev.cuda()
		for layer in self.hidden:
			combined = torch.cat([cur, prev, x], 1)
			prev = cur
			cur = self.activation(layer(combined))
		y = self.outLayer(torch.cat([cur, prev, x], 1))
		return (self.tanh(y)+1)/2 # hey I think this works slightly better
		# return self.sig(y)




class Fourier(nn.Module):
	def __init__(self, fourier_order=4, hidden_size=100, num_hidden_layers=7, linmap: CenteredLinearMap=None, use_cuda: bool = True):
		""" 
		Linear torch model that adds Fourier Features to the initial input x as \
		sin(x) + cos(x), sin(2x) + cos(2x), sin(3x) + cos(3x), ...
		These features are then inputted to a SkipConn network.

		Parameters: 
		fourier_order (int): number fourier features to use. Each addition adds 4x\
		 parameters to each layer.
		hidden_size (float): number of non-skip parameters per hidden layer (SkipConn)
		num_hidden_layers (float): number of hidden layers (SkipConn)
		"""
		super(Fourier,self).__init__()
		self.fourier_order = fourier_order
		self.inner_model = SkipConn(hidden_size, num_hidden_layers, fourier_order*4 + 2, activation=nn.LeakyReLU, use_cuda=use_cuda)
		self._linmap = linmap
		orders = torch.arange(1, fourier_order + 1).float()
		if use_cuda:
			orders = orders.cuda()
		self.orders = orders

	def forward(self,x):
		if self._linmap:
			x = self._linmap.map(x)
		x = x.unsqueeze(-1)  # add an extra dimension for broadcasting
		fourier_features = torch.cat([torch.sin(self.orders * x), torch.cos(self.orders * x), x], dim=-1)
		fourier_features = fourier_features.view(x.shape[0], -1)  # flatten the last two dimensions
		return self.inner_model(fourier_features)


class Fourier2D(nn.Module):
    def __init__(self, fourier_order=4, hidden_size=100, num_hidden_layers=7, linmap: CenteredLinearMap=None,use_cuda: bool=True):
        super(Fourier2D,self).__init__()
        self.fourier_order = fourier_order
        self.inner_model = SkipConn(hidden_size, num_hidden_layers, (fourier_order*fourier_order*4) + 2, activation=nn.LeakyReLU, use_cuda=use_cuda)
        self._linmap = linmap
        orders = torch.arange(0, fourier_order).float()
        if use_cuda:
            orders = orders.cuda()
        self.orders = orders

    def forward(self,x):
        if self._linmap:
            x = self._linmap.map(x)
        features = [x]
        for n in self.orders:
            for m in self.orders:
                features.append((torch.cos(n*x[:,0])*torch.cos(m*x[:,1])).unsqueeze(-1))
                features.append((torch.cos(n*x[:,0])*torch.sin(m*x[:,1])).unsqueeze(-1))
                features.append((torch.sin(n*x[:,0])*torch.cos(m*x[:,1])).unsqueeze(-1))
                features.append((torch.sin(n*x[:,0])*torch.sin(m*x[:,1])).unsqueeze(-1))
        fourier_features = torch.cat(features, 1)
        return self.inner_model(fourier_features)

class CenteredLinearMap():
	def __init__(self, xmin=-2.5, xmax=1.0, ymin=-1.1, ymax=1.1, x_size=None, y_size=None, use_cuda: bool = True):
		if x_size is not None:
			x_m = x_size/(xmax - xmin)
		else: 
			x_m = 1.
		if y_size is not None:
			y_m = y_size/(ymax - ymin)
		else: 
			y_m = 1.
		x_b = -(xmin + xmax)*x_m/2
		y_b = -(ymin + ymax)*y_m/2
		m = torch.tensor([x_m, y_m], dtype=torch.float)
		b = torch.tensor([x_b, y_b], dtype=torch.float)
		self.m = m
		self.b = b
		self.use_cuda = use_cuda

	def map(self, x):
		if self.use_cuda:
			self.m = self.m.cuda()
			self.b = self.b.cuda()
		return self.m*x + self.b
	
# Taylor features, x, x^2, x^3, ...
# surprisingly terrible
class Taylor(nn.Module):
	def __init__(self, taylor_order=4, hidden_size=100, num_hidden_layers=7, linmap=None):
		super(Taylor,self).__init__()
		self.taylor_order = taylor_order
		self._linmap = linmap
		self.inner_model = SkipConn(hidden_size, num_hidden_layers, taylor_order*2 + 2)

	def forward(self,x):
		if self._linmap:
			x = self._linmap.map(x)
		series = [x]
		for n in range(1, self.taylor_order+1):
			series.append(x**n)
		taylor = torch.cat(series, 1)
		return self.inner_model(taylor)

